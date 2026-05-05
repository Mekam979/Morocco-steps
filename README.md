# Morocco Secrets — Guide Touristique du Maroc 🇲🇦

Morocco Secrets est une application web immersive conçue pour faire découvrir la richesse culturelle, historique et naturelle du Maroc. Elle intègre un chatbot intelligent, des cartes interactives et une gestion complète des destinations par catégorie.

## 🚀 Fonctionnalités

- **Exploration par Catégories** : Découvrez les villes côtières, sahariennes, de montagne, culturelles et agricoles.
- **Chatbot Intelligent (Trippy)** : Un assistant IA basé sur Llama-3.3 pour répondre à toutes vos questions sur le Maroc.
- **Détails des Villes** : Informations complètes sur les attractions, restaurants, artisanat et patrimoine vestimentaire.
- **Système de Packs** : Offres gratuites et premium pour des fonctionnalités avancées.
- **Multilingue** : Support complet de plusieurs langues via Google Translate intégré.
- **Interface Premium** : Design responsive avec glassmorphism et esthétique marocaine moderne.

## 🛠️ Stack Technique

- **Backend** : Flask (Python 3.x)
- **Frontend** : HTML5, CSS3 (Vanilla), JavaScript
- **Base de données** : MySQL
- **IA** : Groq API (Llama-3.3)
- **CDN** : Cloudinary (Images)
- **Email** : Flask-Mail

## 📦 Installation

1. **Cloner le projet** :
   ```bash
   git clone https://github.com/Mekam979/Morocco-steps.git
   cd Morocco-steps
   ```

2. **Installer les dépendances** :
   ```bash
   pip install -r backend/requirements.txt
   ```

3. **Configurer l'environnement** :
   - Copiez `backend/.env.example` vers `backend/.env`.
   - Remplissez vos clés API (Groq, Cloudinary, etc.) et vos accès DB.

4. **Lancer l'application** :
   ```bash
   python backend/app.py
   ```

## 📂 Structure du Projet

- `backend/` : Logique serveur, routes, intégration IA et gestion DB.
- `frontend/static/` : Assets CSS, JS, images et vidéos.
- `frontend/templates/` : Templates HTML (Jinja2).

## 📄 Licence

© 2026 Morocco Secrets. Tous droits réservés.
