"""
Trippy — Guide Touristique du Maroc
Avec inscription/connexion par code email (vérification)
"""

from flask import Flask, render_template, abort, request, jsonify, session, send_from_directory
from flask_mail import Mail, Message
import pymysql
import requests
import traceback
import os
import hashlib
import random
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

try:
    from rag_engine import rag_retrieve_and_augment
except ImportError:
    def rag_retrieve_and_augment(message):
        return {"system_prompt": "Expert Maroc", "user_prompt": message,
                "has_context": False, "ville_detec": None, "intent_detec": None}

base_dir = os.path.dirname(os.path.abspath(__file__))
# app.py est dans /backend — frontend est au niveau parent (root)
frontend_dir = os.path.join(os.path.dirname(base_dir), 'frontend')
template_dir = os.path.join(frontend_dir, 'templates')
static_dir = os.path.join(frontend_dir, 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = os.getenv('SECRET_KEY', 'trippy_maroc_secret_key_2026')

# ============================================================
# CONFIGURATION EMAIL
# ============================================================
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_DEFAULT_SENDER'] = app.config['MAIL_USERNAME'] or 'noreply@morocco-secrets.com'

mail = Mail(app)

# ============================================================
# CLOUDINARY HELPER
# ============================================================
CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME', 'darytb39v')
CLOUDINARY_BASE = f"https://res.cloudinary.com/{CLOUDINARY_CLOUD_NAME}/image/upload"

def cloudinary_url(filename, folder=None):
    """
    Converts a local image filename to a Cloudinary URL.
    Usage in Jinja2:
      {{ cloudinary_url(ville.image_path) }}                → root (villes are in root)
      {{ cloudinary_url(art.image_path, 'artisanat') }}     → artisanat/
      {{ cloudinary_url(att.image_path, 'attractions') }}   → attractions/
      {{ cloudinary_url(vest.image_path, 'vestimentaire') }}→ vestimentaire/
      {{ cloudinary_url('trippy.jpg', 'root') }}            → root (UI images)
    """
    if not filename:
        return f"{CLOUDINARY_BASE}/default.jpg"
    if filename.startswith('http'):
        return filename
    # root = no subfolder (villes + UI images)
    if folder == 'root' or folder is None:
        return f"{CLOUDINARY_BASE}/{filename}"
    return f"{CLOUDINARY_BASE}/{folder}/{filename}"

@app.context_processor
def inject_cloudinary():
    return dict(cloudinary_url=cloudinary_url)


GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_MODEL   = "llama-3.3-70b-versatile"

DB_CONFIG = {
    'host':        os.getenv('DB_HOST', 'localhost'),
    'port':        int(os.getenv('DB_PORT', 3306)),
    'user':        os.getenv('DB_USER', 'root'),
    'password':    os.getenv('DB_PASSWORD', ''),
    'db':          os.getenv('DB_NAME', 'tourisme_maroc'),
    'cursorclass': pymysql.cursors.DictCursor,
    'charset':     'utf8mb4',
    'ssl':         {'verify_cert': False}
}

TIER_LIMITS = {
    'explorer': 10,
    'standard': float('inf'),
    'premium':  float('inf')
}

ANON_LIMIT = 3

# ============================================================
# HELPERS DB
# ============================================================
def get_db():
    try:
        return pymysql.connect(**DB_CONFIG)
    except Exception as e:
        print(f"Erreur DB : {e}")
        return None

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def call_groq(system_prompt, user_message):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json"
    }
    payload = {
        "model":    GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message}
        ],
        "temperature": 0.7,
        "max_tokens":  800
    }
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers, json=payload, timeout=20
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Erreur Groq : {e}")
    return None

def save_message(user_id, role, message, ville=None):
    conn = get_db()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_messages (user_id, role, message, ville_detec) VALUES (%s,%s,%s,%s)",
                (user_id, role, message, ville)
            )
        conn.commit()
    except Exception as e:
        print(f"Erreur save_message : {e}")
    finally:
        conn.close()

def get_chat_history(user_id, limit=30):
    conn = get_db()
    if not conn: return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT role, message, ville_detec, created_at
                FROM chat_messages
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (user_id, limit))
            return list(reversed(cur.fetchall()))
    except Exception as e:
        print(f"Erreur get_history : {e}")
        return []
    finally:
        conn.close()

def count_today_messages(user_id):
    conn = get_db()
    if not conn: return 0
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as cnt FROM chat_messages
                WHERE user_id = %s AND role = 'user'
                AND DATE(created_at) = CURDATE()
            """, (user_id,))
            return cur.fetchone()['cnt']
    except:
        return 0
    finally:
        conn.close()

# ============================================================
# EMAIL MASKING
# ============================================================
def mask_email(email):
    if not email or '@' not in email:
        return email
    local, domain = email.split('@', 1)
    if len(local) <= 2:
        masked_local = local[0] + '***'
    else:
        masked_local = local[0] + '***' + local[-1]
    return f"{masked_local}@{domain}"

@app.context_processor
def utility_processor():
    return dict(mask_email=mask_email)

# ============================================================
# ROUTES PAGES
# ============================================================
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/villes')
def index():
    conn = None
    villes = []
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nom_ville, slogan, description, type_ville, image_path "
                "FROM villes ORDER BY nom_ville"
            )
            villes = cur.fetchall()
    except Exception as e:
        print(f"Erreur villes : {e}")
    finally:
        if conn: conn.close()
    return render_template('villes.html', villes=villes, titre_filter="Toutes les villes du Maroc")

@app.route('/filter/<type_ville>')
def filter_villes(type_ville):
    conn = None
    villes = []
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nom_ville, slogan, description, type_ville, image_path "
                "FROM villes WHERE type_ville = %s ORDER BY nom_ville",
                (type_ville,)
            )
            villes = cur.fetchall()
    except Exception as e:
        print(f"Erreur filtre : {e}")
    finally:
        if conn: conn.close()
    return render_template('villes.html', villes=villes, titre_filter=type_ville)

@app.route('/ville/<string:nom>')
def details_ville(nom):
    conn = None
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM villes WHERE nom_ville = %s", (nom,))
            ville = cur.fetchone()
            if not ville: abort(404)

            cur.execute("SELECT nom, description, image_path FROM attractions WHERE nom_ville = %s", (nom,))
            attractions = cur.fetchall()

            cur.execute("SELECT description FROM activites WHERE nom_ville = %s", (nom,))
            activites = cur.fetchall()

            cur.execute("SELECT nom, description, specialites, lien FROM restaurants WHERE nom_ville = %s", (nom,))
            restaurants = cur.fetchall()

            cur.execute("SELECT nom_plat FROM specialites_ville WHERE nom_ville = %s", (nom,))
            specialites = cur.fetchall()

            cur.execute("SELECT nom_artisanat as nom, description, image_path FROM artisanat WHERE nom_ville = %s", (nom,))
            artisanat = cur.fetchall()

            cur.execute("SELECT nom, etoiles, avis, lien FROM hebergements WHERE nom_ville = %s", (nom,))
            hebergements = cur.fetchall()

            cur.execute("SELECT nom, description, image_path FROM patrimoine_vestimentaire WHERE nom_ville = %s", (nom,))
            vetements = cur.fetchall()

            cur.execute("SELECT nom, periode, description FROM evenements WHERE nom_ville = %s", (nom,))
            evenements = cur.fetchall()

            cur.execute("SELECT type FROM transports WHERE nom_ville = %s", (nom,))
            transports = cur.fetchall()

    except Exception as e:
        print(f"Erreur details : {e}")
        abort(500)
    finally:
        if conn: conn.close()

    return render_template('details.html',
        ville=ville, attractions=attractions, activites=activites,
        restaurants=restaurants, specialites=specialites,
        artisanat=artisanat, hebergements=hebergements,
        vetements=vetements, evenements=evenements,
        transports=transports)

@app.route('/pricing')
def pricing():
    return render_template('pricing.html')

# ============================================================
# AUTHENTIFICATION (avec code email)
# ============================================================

def send_code_email(email, code, purpose="inscription"):
    subject = f"🔐 Code de vérification - Morocco Secrets ({purpose})"
    body = f"""
Bonjour,

Votre code de vérification pour {purpose} est : {code}

Ce code expirera dans 10 minutes.

Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.

Merci de votre confiance.
"""
    try:
        msg = Message(subject, recipients=[email], body=body)
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Erreur envoi email : {e}")
        traceback.print_exc()
        return False

# ---------- Étape 1 : Envoyer code pour inscription ----------
@app.route('/send-verification', methods=['POST'])
def send_verification():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    
    if not email:
        return jsonify({'success': False, 'message': 'Email requis.'})
    
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'Cet email est déjà utilisé.'})
    conn.close()
    
    # Générer code 6 chiffres
    code = f"{random.randint(100000, 999999)}"
    expiry = datetime.now() + timedelta(minutes=10)
    
    # Stocker en session
    session['temp_email'] = email
    session['temp_code'] = code
    session['temp_expiry'] = expiry.isoformat()
    session['temp_purpose'] = 'register'
    
    if send_code_email(email, code, "inscription"):
        return jsonify({'success': True, 'message': 'Code envoyé par email.'})
    else:
        return jsonify({'success': False, 'message': "Erreur d'envoi d'email. Vérifiez la configuration SMTP."})

# ---------- Étape 2 : Vérifier code (inscription ou reset) ----------
@app.route('/verify-code', methods=['POST'])
def verify_code():
    data = request.get_json()
    user_code = data.get('code', '').strip()
    
    temp_code = session.get('temp_code')
    temp_expiry = session.get('temp_expiry')
    email = session.get('temp_email')
    purpose = session.get('temp_purpose')
    
    if not temp_code or not email or not temp_expiry:
        return jsonify({'success': False, 'message': 'Aucune demande de vérification en cours.'})
    
    if datetime.now() > datetime.fromisoformat(temp_expiry):
        session.pop('temp_code', None)
        session.pop('temp_email', None)
        session.pop('temp_expiry', None)
        session.pop('temp_purpose', None)
        return jsonify({'success': False, 'message': 'Code expiré. Recommencez.'})
    
    if user_code != temp_code:
        return jsonify({'success': False, 'message': 'Code incorrect.'})
    
    # Code valide
    if purpose == 'register':
        session['verified_email'] = email
    elif purpose == 'reset':
        session['reset_email'] = email
    
    session.pop('temp_code', None)
    session.pop('temp_expiry', None)
    session.pop('temp_purpose', None)
    
    return jsonify({'success': True, 'message': 'Email vérifié. Vous pouvez continuer.'})

# ---------- Étape 3 : Finaliser inscription ----------
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    nom = data.get('nom', '').strip()
    password = data.get('password', '').strip()
    
    email = session.get('verified_email')
    if not email:
        return jsonify({'success': False, 'message': 'Veuillez d abord vérifier votre email.'})
    
    if not nom or not password:
        return jsonify({'success': False, 'message': 'Nom et mot de passe requis.'})
    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Mot de passe trop court.'})
    
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (nom, email, password_hash, tier, msg_count, email_verified) VALUES (%s,%s,%s,'explorer',0,TRUE)",
                (nom, email, hash_password(password))
            )
            conn.commit()
            user_id = cur.lastrowid
    except Exception as e:
        print(f"Erreur inscription : {e}")
        return jsonify({'success': False, 'message': 'Erreur lors de l\'inscription.'})
    finally:
        conn.close()
    
    session.pop('verified_email', None)
    session.clear()  # Nettoyer toute session existante
    session['user_id'] = user_id
    session['user_nom'] = nom
    session['user_email'] = email
    session['user_tier'] = 'explorer'
    session.pop('anon_msg_count', None)
    
    return jsonify({'success': True, 'message': f'Bienvenue {nom} !', 'nom': nom, 'tier': 'explorer', 'email': email})

# ---------- Connexion classique ----------
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()

    if not email or not password:
        return jsonify({'success': False, 'message': 'Email et mot de passe requis.'})

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM users WHERE email = %s AND password_hash = %s",
                (email, hash_password(password))
            )
            user = cur.fetchone()

        if not user:
            return jsonify({'success': False, 'message': 'Email ou mot de passe incorrect.'})

        session.clear()
        session['user_id'] = user['id']
        session['user_nom'] = user['nom']
        session['user_email'] = user['email']
        session['user_tier'] = user['tier']
        session.pop('anon_msg_count', None)

        history = get_chat_history(user['id'], limit=30)
        msg_count = count_today_messages(user['id'])

        return jsonify({
            'success':   True,
            'message':   f"Bon retour {user['nom']} !",
            'nom':       user['nom'],
            'tier':      user['tier'],
            'email':     user['email'],
            'msg_count': msg_count,
            'history':   [{'role': m['role'], 'message': m['message']} for m in history]
        })
    except Exception as e:
        print(f"Erreur login : {e}")
        return jsonify({'success': False, 'message': 'Erreur serveur.'})
    finally:
        conn.close()

# ---------- Mot de passe oublié : envoyer code ----------
@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    
    if not email:
        return jsonify({'success': False, 'message': 'Email requis.'})
    
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        if not user:
            conn.close()
            return jsonify({'success': False, 'message': 'Aucun compte avec cet email.'})
    conn.close()
    
    code = f"{random.randint(100000, 999999)}"
    expiry = datetime.now() + timedelta(minutes=10)
    
    session['temp_email'] = email
    session['temp_code'] = code
    session['temp_expiry'] = expiry.isoformat()
    session['temp_purpose'] = 'reset'
    
    if send_code_email(email, code, "réinitialisation du mot de passe"):
        return jsonify({'success': True, 'message': 'Code envoyé par email.'})
    else:
        return jsonify({'success': False, 'message': "Erreur d'envoi d'email."})

# ---------- Réinitialiser mot de passe ----------
@app.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    new_password = data.get('password', '').strip()
    
    email = session.get('reset_email')
    if not email:
        return jsonify({'success': False, 'message': 'Aucune demande de réinitialisation.'})
    
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'Mot de passe trop court.'})
    
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE email = %s",
                (hash_password(new_password), email)
            )
            conn.commit()
    except Exception as e:
        print(f"Erreur reset : {e}")
        return jsonify({'success': False, 'message': 'Erreur lors de la réinitialisation.'})
    finally:
        conn.close()
    
    session.pop('reset_email', None)
    return jsonify({'success': True, 'message': 'Mot de passe mis à jour. Connectez-vous.'})

# ---------- Déconnexion ----------
@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/me')
def me():
    if 'user_id' not in session:
        return jsonify({'logged': False, 'anon_count': session.get('anon_msg_count', 0)})
    user_id = session.get('user_id')
    msg_count = count_today_messages(user_id)
    return jsonify({
        'logged':    True,
        'nom':       session.get('user_nom'),
        'email':     session.get('user_email'),
        'tier':      session.get('user_tier'),
        'msg_count': msg_count
    })

# ============================================================
# CHATBOT
# ============================================================
@app.route('/chat', methods=['POST'])
def chat():
    try:
        data    = request.get_json()
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'response': "Veuillez ecrire un message !"})

        user_id   = session.get('user_id')
        user_tier = session.get('user_tier', 'explorer')

        if not user_id:
            anon_count = session.get('anon_msg_count', 0)
            if anon_count >= ANON_LIMIT:
                return jsonify({'response': None, 'need_register': True})
            session['anon_msg_count'] = anon_count + 1
        elif user_tier == 'explorer':
            count_today = count_today_messages(user_id)
            if count_today >= TIER_LIMITS['explorer']:
                return jsonify({'response': f'Limite atteinte. Passez au pack Voyageur Pro !', 'limit_reached': True})

        limit_info = None
        if not user_id:
            used = session.get('anon_msg_count', 0)
            limit_info = f"L'utilisateur est en mode anonyme. Message {used}/{ANON_LIMIT}. Rappelle-lui de s'inscrire pour ne pas perdre l'accès."
        elif user_tier == 'explorer':
            used = count_today_messages(user_id)
            remaining = int(TIER_LIMITS['explorer']) - used
            if remaining <= 2:
                limit_info = f"Il reste {remaining} messages à l'utilisateur aujourd'hui. Suggère-lui de passer au pack Voyageur Pro."

        rag = rag_retrieve_and_augment(message, limit_info)
        response_text = call_groq(rag['system_prompt'], rag['user_prompt'])
        if not response_text:
            response_text = "Désolé, erreur technique."

        if user_id:
            save_message(user_id, 'user', message, rag.get('ville_detec'))
            save_message(user_id, 'bot', response_text, rag.get('ville_detec'))

        ville_detec = rag.get('ville_detec')
        intent_detec = rag.get('intent_detec')

        result = {'response': response_text, 'ville': ville_detec, 'intent': intent_detec}
        if not user_id:
            used = session.get('anon_msg_count', 0)
            remaining = ANON_LIMIT - used
            result['anon_remaining'] = remaining
            if remaining <= 0:
                result['need_register'] = True
        elif user_tier == 'explorer':
            used = count_today_messages(user_id)
            result['msg_count'] = used
        else:
            result['msg_count'] = count_today_messages(user_id)
        return jsonify(result)
    except Exception:
        traceback.print_exc()
        return jsonify({'response': "Erreur interne."})

@app.route('/chat/history')
def chat_history():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'history': [], 'logged': False})
    history = get_chat_history(user_id, limit=30)
    return jsonify({'logged': True, 'history': [{'role': m['role'], 'message': m['message']} for m in history]})

@app.route('/chat/clear', methods=['POST'])
def clear_chat_history():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False})
    conn = get_db()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chat_messages WHERE user_id = %s", (user_id,))
            conn.commit()
        finally:
            conn.close()
    return jsonify({'success': True})

# ============================================================
# MEDIAS
# ============================================================
@app.route('/static/videos/<path:filename>')
def serve_video(filename):
    return send_from_directory(os.path.join(frontend_dir, 'static', 'videos'), filename, mimetype='video/mp4')

@app.route('/static/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(os.path.join(frontend_dir, 'static', 'images'), filename)

# ============================================================
# TIERS & TESTS
# ============================================================
@app.route('/set-tier/<tier>')
def set_tier(tier):
    if tier in ('explorer', 'standard', 'premium'):
        session['user_tier'] = tier
        user_id = session.get('user_id')
        if user_id:
            conn = get_db()
            if conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE users SET tier = %s WHERE id = %s", (tier, user_id))
                    conn.commit()
                finally:
                    conn.close()
        return jsonify({'status': 'success', 'tier': tier})
    return jsonify({'status': 'error'})

@app.route('/test-db')
def test_db():
    result = {'status': 'error', 'tables': []}
    conn = get_db()
    if not conn:
        result['message'] = "Connexion impossible"
        return jsonify(result)
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            result['tables'] = [list(t.values())[0] for t in cur.fetchall()]
            cur.execute("SELECT COUNT(*) as c FROM villes")
            result['nb_villes'] = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM users")
            result['nb_users'] = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM chat_messages")
            result['nb_messages'] = cur.fetchone()['c']
            result['status'] = 'success'
            result['message'] = "Connexion MySQL réussie"
    except Exception as e:
        result['message'] = str(e)
    finally:
        conn.close()
    return jsonify(result)

if __name__ == '__main__':
    print("=" * 55)
    print("Trippy — Guide Touristique Maroc (avec vérification email)")
    print("=" * 55)
    print(f"  Modèle   : {GROQ_MODEL}")
    print(f"  Anon     : {ANON_LIMIT} messages gratuits")
    print(f"  Explorer : {int(TIER_LIMITS['explorer'])} messages/jour")
    print("=" * 55)
    # v1.0.1 - Vercel Deployment Force
    app.run(debug=True, port=5001)