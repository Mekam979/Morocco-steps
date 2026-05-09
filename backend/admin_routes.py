"""
Admin Blueprint — auth + villes CRUD.

Routes:
    GET/POST /admin/login
    GET      /admin/logout
    GET      /admin/dashboard
    GET      /admin/villes
    GET/POST /admin/villes/new
    GET/POST /admin/villes/<nom_ville>/edit
    POST     /admin/villes/<nom_ville>/delete
"""

import os
import secrets
import unicodedata
from functools import wraps
from urllib.parse import unquote

import cloudinary
import cloudinary.exceptions
import cloudinary.uploader
from flask import (
    Blueprint, flash, render_template, request, redirect, url_for, session
)

from db import get_connection

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

TYPE_VILLE_OPTIONS = [
    "Villes côtières",
    "Villes sahariennes",
    "Villes culturelles",
    "Villes de montagne",
    "Villes agricoles",
]

ACCENT_MAP = {
    "é": "e", "è": "e", "ê": "e", "ë": "e",
    "â": "a", "à": "a", "ä": "a",
    "ô": "o", "ö": "o",
    "û": "u", "ù": "u", "ü": "u",
    "î": "i", "ï": "i",
    "ç": "c",
}


def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    for k, v in ACCENT_MAP.items():
        s = s.replace(k, v)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = s.replace(" ", "_")
    s = "".join(c for c in s if c.isalnum() or c == "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def _ensure_google_maps_link_column():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'villes' "
                "AND COLUMN_NAME = 'google_maps_link'"
            )
            if cur.fetchone()["n"] == 0:
                cur.execute(
                    "ALTER TABLE villes ADD COLUMN google_maps_link VARCHAR(500) NULL"
                )
                conn.commit()
                print("[admin] added column villes.google_maps_link")
    finally:
        conn.close()


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return wrapper


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin"):
        return redirect(url_for("admin.dashboard"))

    error = None
    if request.method == "POST":
        submitted = request.form.get("password", "")
        expected = os.getenv("ADMIN_PASSWORD", "")
        if expected and secrets.compare_digest(submitted, expected):
            session["admin"] = True
            return redirect(url_for("admin.dashboard"))
        error = "Mot de passe incorrect."

    return render_template("admin/login.html", error=error)


@admin_bp.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("admin.login"))


@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    return render_template("admin/dashboard.html")


@admin_bp.route("/villes")
@admin_required
def villes_list():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nom_ville, type_ville, image_path FROM villes "
                "ORDER BY nom_ville"
            )
            villes = cur.fetchall()
    finally:
        conn.close()
    return render_template("admin/villes_list.html", villes=villes)


# ---------------------------------------------------------------------------
# Villes CRUD — new / edit / delete
# ---------------------------------------------------------------------------


def _legacy_type_ville_for(value):
    """Return value only if it is non-standard (not in TYPE_VILLE_OPTIONS, case-insensitive)."""
    if not value:
        return None
    normalized = [opt.lower() for opt in TYPE_VILLE_OPTIONS]
    if value.lower() in normalized:
        return None  # it IS a known option — no legacy needed
    return value


def _validate_form(form, mode, current_nom=None):
    """Returns (raw, errors). raw holds string values for re-rendering."""
    raw = {
        "nom_ville":
            (form.get("nom_ville") or "").strip() if mode == "new" else current_nom,
        "slogan": (form.get("slogan") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "type_ville": (form.get("type_ville") or "").strip(),
        "latitude": (form.get("latitude") or "").strip(),
        "longitude": (form.get("longitude") or "").strip(),
        "google_maps_link": (form.get("google_maps_link") or "").strip(),
    }
    errors = {}

    if mode == "new":
        if not raw["nom_ville"]:
            errors["nom_ville"] = "Nom requis."
        elif len(raw["nom_ville"]) > 120:
            errors["nom_ville"] = "Maximum 120 caractères."
        else:
            conn = get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM villes WHERE nom_ville = %s",
                        (raw["nom_ville"],),
                    )
                    if cur.fetchone():
                        errors["nom_ville"] = "Une ville avec ce nom existe déjà."
            finally:
                conn.close()

    if len(raw["slogan"]) > 60:
        errors["slogan"] = "Maximum 60 caractères."

    if raw["latitude"]:
        try:
            lat = float(raw["latitude"])
            if not -90 <= lat <= 90:
                errors["latitude"] = "Doit être entre -90 et 90."
        except ValueError:
            errors["latitude"] = "Doit être un nombre valide."

    if raw["longitude"]:
        try:
            lon = float(raw["longitude"])
            if not -180 <= lon <= 180:
                errors["longitude"] = "Doit être entre -180 et 180."
        except ValueError:
            errors["longitude"] = "Doit être un nombre valide."

    if raw["google_maps_link"] and not raw["google_maps_link"].startswith(
        ("http://", "https://")
    ):
        errors["google_maps_link"] = "Doit commencer par http:// ou https://."

    return raw, errors


def _to_db(raw):
    return {
        "nom_ville": raw["nom_ville"],
        "slogan": raw["slogan"] or None,
        "description": raw["description"] or None,
        "type_ville": raw["type_ville"] or None,
        "latitude": float(raw["latitude"]) if raw["latitude"] else None,
        "longitude": float(raw["longitude"]) if raw["longitude"] else None,
        "google_maps_link": raw["google_maps_link"] or None,
    }


def _upload_image_if_present(file_storage, slug, folder="villes"):
    """Returns (image_path, error). image_path None means no upload requested."""
    if not file_storage or not file_storage.filename:
        return None, None
    try:
        result = cloudinary.uploader.upload(
            file_storage,
            public_id=f"{folder}/{slug}",
            overwrite=True,
            resource_type="image",
        )
        return f"{slug}.{result.get('format', 'jpg')}", None
    except cloudinary.exceptions.Error as e:
        return None, str(e)


def _detail_redirect(nom_ville, tab):
    return redirect(
        url_for("admin.villes_detail", nom_ville=nom_ville) + f"#{tab}"
    )


def _render_form(mode, raw, errors, image_path=None):
    return render_template(
        "admin/villes_form.html",
        mode=mode,
        v={**raw, "image_path": image_path},
        errors=errors,
        type_ville_options=TYPE_VILLE_OPTIONS,
        legacy_type_ville=_legacy_type_ville_for(raw.get("type_ville")),
    )


@admin_bp.route("/villes/new", methods=["GET", "POST"])
@admin_required
def villes_new():
    if request.method == "GET":
        empty = {k: "" for k in (
            "nom_ville", "slogan", "description", "type_ville",
            "latitude", "longitude", "google_maps_link",
        )}
        return _render_form("new", empty, {})

    raw, errors = _validate_form(request.form, mode="new")
    if errors:
        return _render_form("new", raw, errors)

    slug = slugify(raw["nom_ville"])
    image_path, upload_err = _upload_image_if_present(request.files.get("image"), slug)
    if upload_err:
        errors["_form"] = f"Erreur d'upload Cloudinary : {upload_err}"
        return _render_form("new", raw, errors)

    db = _to_db(raw)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO villes (nom_ville, slogan, description, type_ville, "
                "latitude, longitude, image_path, google_maps_link) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (db["nom_ville"], db["slogan"], db["description"], db["type_ville"],
                 db["latitude"], db["longitude"], image_path, db["google_maps_link"]),
            )
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("admin.villes_list"))


@admin_bp.route("/villes/<nom_ville>/edit", methods=["GET", "POST"])
@admin_required
def villes_edit(nom_ville):
    nom_ville = unquote(nom_ville)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nom_ville, slogan, description, type_ville, latitude, "
                "longitude, image_path, google_maps_link "
                "FROM villes WHERE nom_ville = %s",
                (nom_ville,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return redirect(url_for("admin.villes_list"))

    if request.method == "GET":
        raw = {
            "nom_ville": row["nom_ville"],
            "slogan": row["slogan"] or "",
            "description": row["description"] or "",
            "type_ville": row["type_ville"] or "",
            "latitude": "" if row["latitude"] is None else str(row["latitude"]),
            "longitude": "" if row["longitude"] is None else str(row["longitude"]),
            "google_maps_link": row["google_maps_link"] or "",
        }
        return _render_form("edit", raw, {}, image_path=row["image_path"])

    raw, errors = _validate_form(request.form, mode="edit", current_nom=nom_ville)
    if errors:
        return _render_form("edit", raw, errors, image_path=row["image_path"])

    slug = slugify(nom_ville)
    new_image_path, upload_err = _upload_image_if_present(
        request.files.get("image"), slug
    )
    if upload_err:
        errors["_form"] = f"Erreur d'upload Cloudinary : {upload_err}"
        return _render_form("edit", raw, errors, image_path=row["image_path"])
    image_path = new_image_path or row["image_path"]

    db = _to_db(raw)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE villes SET slogan=%s, description=%s, type_ville=%s, "
                "latitude=%s, longitude=%s, image_path=%s, google_maps_link=%s "
                "WHERE nom_ville=%s",
                (db["slogan"], db["description"], db["type_ville"],
                 db["latitude"], db["longitude"], image_path,
                 db["google_maps_link"], nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("admin.villes_list"))


@admin_bp.route("/villes/<nom_ville>/detail")
@admin_required
def villes_detail(nom_ville):
    nom_ville = unquote(nom_ville)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nom_ville, slogan, description, type_ville, latitude, "
                "longitude, image_path, google_maps_link "
                "FROM villes WHERE nom_ville = %s", (nom_ville,))
            ville = cur.fetchone()
            if not ville:
                return redirect(url_for("admin.villes_list"))

            cur.execute(
                "SELECT id, nom, description, image_path FROM attractions "
                "WHERE nom_ville = %s ORDER BY id", (nom_ville,))
            attractions = cur.fetchall()

            cur.execute(
                "SELECT id, nom_plat FROM specialites_ville "
                "WHERE nom_ville = %s ORDER BY id", (nom_ville,))
            specialites = cur.fetchall()

            cur.execute(
                "SELECT id, nom, description, specialites, lien FROM restaurants "
                "WHERE nom_ville = %s ORDER BY id", (nom_ville,))
            restaurants = cur.fetchall()

            cur.execute(
                "SELECT id, nom_artisanat, description, image_path FROM artisanat "
                "WHERE nom_ville = %s ORDER BY id", (nom_ville,))
            artisanat = cur.fetchall()

            cur.execute(
                "SELECT id, nom, description, image_path FROM patrimoine_vestimentaire "
                "WHERE nom_ville = %s ORDER BY id", (nom_ville,))
            vestimentaire = cur.fetchall()

            cur.execute(
                "SELECT id, nom, etoiles, avis, lien FROM hebergements "
                "WHERE nom_ville = %s ORDER BY id", (nom_ville,))
            hebergements = cur.fetchall()

            cur.execute(
                "SELECT id, nom, periode, description FROM evenements "
                "WHERE nom_ville = %s ORDER BY id", (nom_ville,))
            evenements = cur.fetchall()

            cur.execute(
                "SELECT id, type FROM transports "
                "WHERE nom_ville = %s ORDER BY id", (nom_ville,))
            transports = cur.fetchall()
    finally:
        conn.close()

    return render_template(
        "admin/villes_detail.html",
        ville=ville,
        attractions=attractions,
        specialites=specialites,
        restaurants=restaurants,
        artisanat=artisanat,
        vestimentaire=vestimentaire,
        hebergements=hebergements,
        evenements=evenements,
        transports=transports,
    )


@admin_bp.route("/villes/<nom_ville>/delete", methods=["POST"])
@admin_required
def villes_delete(nom_ville):
    nom_ville = unquote(nom_ville)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM villes WHERE nom_ville = %s", (nom_ville,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("admin.villes_list"))


# ---------------------------------------------------------------------------
# Attractions CRUD (inline on the villes_detail page)
# ---------------------------------------------------------------------------


def _validate_attraction(form):
    nom = (form.get("nom") or "").strip()
    description = (form.get("description") or "").strip() or None
    if not nom:
        return None, None, "Le nom est requis."
    if len(nom) > 120:
        return None, None, "Le nom dépasse 120 caractères."
    return nom, description, None


@admin_bp.route("/villes/<nom_ville>/attractions/new", methods=["POST"])
@admin_required
def attractions_new(nom_ville):
    nom_ville = unquote(nom_ville)
    nom, description, err = _validate_attraction(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "attractions")

    slug = slugify(nom)
    image_path, upload_err = _upload_image_if_present(
        request.files.get("image"), slug, folder="attractions"
    )
    if upload_err:
        flash(f"Erreur d'upload Cloudinary : {upload_err}", "error")
        return _detail_redirect(nom_ville, "attractions")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO attractions (nom_ville, nom, description, image_path) "
                "VALUES (%s, %s, %s, %s)",
                (nom_ville, nom, description, image_path),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Attraction ajoutée.", "success")
    return _detail_redirect(nom_ville, "attractions")


@admin_bp.route("/villes/<nom_ville>/attractions/<int:id>/edit", methods=["POST"])
@admin_required
def attractions_edit(nom_ville, id):
    nom_ville = unquote(nom_ville)
    nom, description, err = _validate_attraction(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "attractions")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT image_path FROM attractions "
                "WHERE id = %s AND nom_ville = %s",
                (id, nom_ville),
            )
            current = cur.fetchone()
            if not current:
                flash("Attraction introuvable.", "error")
                return _detail_redirect(nom_ville, "attractions")

            slug = slugify(nom)
            new_image, upload_err = _upload_image_if_present(
                request.files.get("image"), slug, folder="attractions"
            )
            if upload_err:
                flash(f"Erreur d'upload Cloudinary : {upload_err}", "error")
                return _detail_redirect(nom_ville, "attractions")
            image_path = new_image or current["image_path"]

            cur.execute(
                "UPDATE attractions SET nom=%s, description=%s, image_path=%s "
                "WHERE id=%s AND nom_ville=%s",
                (nom, description, image_path, id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Attraction modifiée.", "success")
    return _detail_redirect(nom_ville, "attractions")


@admin_bp.route("/villes/<nom_ville>/attractions/<int:id>/delete", methods=["POST"])
@admin_required
def attractions_delete(nom_ville, id):
    nom_ville = unquote(nom_ville)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM attractions WHERE id = %s AND nom_ville = %s",
                (id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Attraction supprimée.", "success")
    return _detail_redirect(nom_ville, "attractions")


# ---------------------------------------------------------------------------
# Spécialités CRUD (specialites_ville table)
# ---------------------------------------------------------------------------


def _validate_specialite(form):
    nom_plat = (form.get("nom_plat") or "").strip()
    if not nom_plat:
        return None, "Le nom du plat est requis."
    if len(nom_plat) > 200:
        return None, "Trop long (max 200 caractères)."
    return nom_plat, None


@admin_bp.route("/villes/<nom_ville>/specialites/new", methods=["POST"])
@admin_required
def specialites_new(nom_ville):
    nom_ville = unquote(nom_ville)
    nom_plat, err = _validate_specialite(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "specialites")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO specialites_ville (nom_ville, nom_plat) VALUES (%s, %s)",
                (nom_ville, nom_plat),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Spécialité ajoutée.", "success")
    return _detail_redirect(nom_ville, "specialites")


@admin_bp.route("/villes/<nom_ville>/specialites/<int:id>/edit", methods=["POST"])
@admin_required
def specialites_edit(nom_ville, id):
    nom_ville = unquote(nom_ville)
    nom_plat, err = _validate_specialite(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "specialites")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE specialites_ville SET nom_plat=%s "
                "WHERE id=%s AND nom_ville=%s",
                (nom_plat, id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Spécialité modifiée.", "success")
    return _detail_redirect(nom_ville, "specialites")


@admin_bp.route("/villes/<nom_ville>/specialites/<int:id>/delete", methods=["POST"])
@admin_required
def specialites_delete(nom_ville, id):
    nom_ville = unquote(nom_ville)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM specialites_ville WHERE id=%s AND nom_ville=%s",
                (id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Spécialité supprimée.", "success")
    return _detail_redirect(nom_ville, "specialites")


# ---------------------------------------------------------------------------
# Événements CRUD (evenements table)
# ---------------------------------------------------------------------------


def _validate_evenement(form):
    nom = (form.get("nom") or "").strip()
    periode = (form.get("periode") or "").strip()
    description = (form.get("description") or "").strip() or None
    if not nom:
        return None, None, None, "Le nom est requis."
    if len(nom) > 100:
        return None, None, None, "Le nom dépasse 100 caractères."
    if len(periode) > 50:
        return None, None, None, "La période dépasse 50 caractères."
    return nom, (periode or None), description, None


@admin_bp.route("/villes/<nom_ville>/evenements/new", methods=["POST"])
@admin_required
def evenements_new(nom_ville):
    nom_ville = unquote(nom_ville)
    nom, periode, description, err = _validate_evenement(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "evenements")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO evenements (nom_ville, nom, periode, description) "
                "VALUES (%s, %s, %s, %s)",
                (nom_ville, nom, periode, description),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Événement ajouté.", "success")
    return _detail_redirect(nom_ville, "evenements")


@admin_bp.route("/villes/<nom_ville>/evenements/<int:id>/edit", methods=["POST"])
@admin_required
def evenements_edit(nom_ville, id):
    nom_ville = unquote(nom_ville)
    nom, periode, description, err = _validate_evenement(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "evenements")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE evenements SET nom=%s, periode=%s, description=%s "
                "WHERE id=%s AND nom_ville=%s",
                (nom, periode, description, id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Événement modifié.", "success")
    return _detail_redirect(nom_ville, "evenements")


@admin_bp.route("/villes/<nom_ville>/evenements/<int:id>/delete", methods=["POST"])
@admin_required
def evenements_delete(nom_ville, id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM evenements WHERE id=%s AND nom_ville=%s",
                (id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Événement supprimé.", "success")
    return _detail_redirect(nom_ville, "evenements")


# ---------------------------------------------------------------------------
# Transport CRUD — add + delete only (no edit per spec)
# ---------------------------------------------------------------------------


def _validate_transport(form):
    type_ = (form.get("type") or "").strip()
    if not type_:
        return None, "Le type est requis."
    if len(type_) > 200:
        return None, "Trop long (max 200 caractères)."
    return type_, None


@admin_bp.route("/villes/<nom_ville>/transports/new", methods=["POST"])
@admin_required
def transports_new(nom_ville):
    type_, err = _validate_transport(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "transport")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO transports (nom_ville, type) VALUES (%s, %s)",
                (nom_ville, type_),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Transport ajouté.", "success")
    return _detail_redirect(nom_ville, "transport")


@admin_bp.route("/villes/<nom_ville>/transports/<int:id>/delete", methods=["POST"])
@admin_required
def transports_delete(nom_ville, id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM transports WHERE id=%s AND nom_ville=%s",
                (id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Transport supprimé.", "success")
    return _detail_redirect(nom_ville, "transport")


# ---------------------------------------------------------------------------
# Restaurants CRUD
# ---------------------------------------------------------------------------


def _validate_lien(raw):
    """Returns (value_or_none, error_or_none)."""
    if not raw:
        return None, None
    if not raw.startswith(("http://", "https://")):
        return None, "Doit commencer par http:// ou https://."
    if len(raw) > 255:
        return None, "Trop long (max 255 caractères)."
    return raw, None


def _validate_restaurant(form):
    nom = (form.get("nom") or "").strip()
    description = (form.get("description") or "").strip() or None
    specialites = (form.get("specialites") or "").strip()
    lien_raw = (form.get("lien") or "").strip()

    if not nom:
        return None, "Le nom est requis."
    if len(nom) > 150:
        return None, "Le nom dépasse 150 caractères."
    if specialites and len(specialites) > 100:
        return None, "Spécialités dépasse 100 caractères."

    lien, lerr = _validate_lien(lien_raw)
    if lerr:
        return None, lerr

    return {
        "nom": nom,
        "description": description,
        "specialites": specialites or None,
        "lien": lien,
    }, None


@admin_bp.route("/villes/<nom_ville>/restaurants/new", methods=["POST"])
@admin_required
def restaurants_new(nom_ville):
    data, err = _validate_restaurant(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "restaurants")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO restaurants (nom_ville, nom, description, "
                "specialites, lien) VALUES (%s, %s, %s, %s, %s)",
                (nom_ville, data["nom"], data["description"],
                 data["specialites"], data["lien"]),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Restaurant ajouté.", "success")
    return _detail_redirect(nom_ville, "restaurants")


@admin_bp.route("/villes/<nom_ville>/restaurants/<int:id>/edit", methods=["POST"])
@admin_required
def restaurants_edit(nom_ville, id):
    data, err = _validate_restaurant(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "restaurants")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE restaurants SET nom=%s, description=%s, "
                "specialites=%s, lien=%s WHERE id=%s AND nom_ville=%s",
                (data["nom"], data["description"], data["specialites"],
                 data["lien"], id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Restaurant modifié.", "success")
    return _detail_redirect(nom_ville, "restaurants")


@admin_bp.route("/villes/<nom_ville>/restaurants/<int:id>/delete", methods=["POST"])
@admin_required
def restaurants_delete(nom_ville, id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM restaurants WHERE id=%s AND nom_ville=%s",
                (id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Restaurant supprimé.", "success")
    return _detail_redirect(nom_ville, "restaurants")


# ---------------------------------------------------------------------------
# Hébergements CRUD
# ---------------------------------------------------------------------------


def _validate_hebergement(form):
    nom = (form.get("nom") or "").strip()
    etoiles = (form.get("etoiles") or "").strip()
    avis = (form.get("avis") or "").strip() or None
    lien_raw = (form.get("lien") or "").strip()

    if not nom:
        return None, "Le nom est requis."
    if len(nom) > 500:
        return None, "Le nom dépasse 500 caractères."
    if len(etoiles) > 20:
        return None, "Étoiles dépasse 20 caractères."

    lien, lerr = _validate_lien(lien_raw)
    if lerr:
        return None, lerr

    return {
        "nom": nom,
        "etoiles": etoiles or None,
        "avis": avis,
        "lien": lien,
    }, None


@admin_bp.route("/villes/<nom_ville>/hebergements/new", methods=["POST"])
@admin_required
def hebergements_new(nom_ville):
    data, err = _validate_hebergement(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "hebergements")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO hebergements (nom_ville, nom, etoiles, avis, lien) "
                "VALUES (%s, %s, %s, %s, %s)",
                (nom_ville, data["nom"], data["etoiles"],
                 data["avis"], data["lien"]),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Hébergement ajouté.", "success")
    return _detail_redirect(nom_ville, "hebergements")


@admin_bp.route("/villes/<nom_ville>/hebergements/<int:id>/edit", methods=["POST"])
@admin_required
def hebergements_edit(nom_ville, id):
    data, err = _validate_hebergement(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "hebergements")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE hebergements SET nom=%s, etoiles=%s, avis=%s, lien=%s "
                "WHERE id=%s AND nom_ville=%s",
                (data["nom"], data["etoiles"], data["avis"],
                 data["lien"], id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Hébergement modifié.", "success")
    return _detail_redirect(nom_ville, "hebergements")


@admin_bp.route("/villes/<nom_ville>/hebergements/<int:id>/delete", methods=["POST"])
@admin_required
def hebergements_delete(nom_ville, id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM hebergements WHERE id=%s AND nom_ville=%s",
                (id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Hébergement supprimé.", "success")
    return _detail_redirect(nom_ville, "hebergements")


# ---------------------------------------------------------------------------
# Artisanat CRUD
# ---------------------------------------------------------------------------


def _validate_artisanat(form):
    nom = (form.get("nom_artisanat") or "").strip()
    description = (form.get("description") or "").strip() or None
    if not nom:
        return None, None, "Le nom est requis."
    if len(nom) > 200:
        return None, None, "Le nom dépasse 200 caractères."
    return nom, description, None


@admin_bp.route("/villes/<nom_ville>/artisanat/new", methods=["POST"])
@admin_required
def artisanat_new(nom_ville):
    nom, description, err = _validate_artisanat(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "artisanat")

    slug = slugify(nom)
    image_path, upload_err = _upload_image_if_present(
        request.files.get("image"), slug, folder="artisanat"
    )
    if upload_err:
        flash(f"Erreur d'upload Cloudinary : {upload_err}", "error")
        return _detail_redirect(nom_ville, "artisanat")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO artisanat (nom_ville, nom_artisanat, description, "
                "image_path) VALUES (%s, %s, %s, %s)",
                (nom_ville, nom, description, image_path),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Artisanat ajouté.", "success")
    return _detail_redirect(nom_ville, "artisanat")


@admin_bp.route("/villes/<nom_ville>/artisanat/<int:id>/edit", methods=["POST"])
@admin_required
def artisanat_edit(nom_ville, id):
    nom, description, err = _validate_artisanat(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "artisanat")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT image_path FROM artisanat "
                "WHERE id=%s AND nom_ville=%s",
                (id, nom_ville),
            )
            current = cur.fetchone()
            if not current:
                flash("Artisanat introuvable.", "error")
                return _detail_redirect(nom_ville, "artisanat")

            slug = slugify(nom)
            new_image, upload_err = _upload_image_if_present(
                request.files.get("image"), slug, folder="artisanat"
            )
            if upload_err:
                flash(f"Erreur d'upload Cloudinary : {upload_err}", "error")
                return _detail_redirect(nom_ville, "artisanat")
            image_path = new_image or current["image_path"]

            cur.execute(
                "UPDATE artisanat SET nom_artisanat=%s, description=%s, "
                "image_path=%s WHERE id=%s AND nom_ville=%s",
                (nom, description, image_path, id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Artisanat modifié.", "success")
    return _detail_redirect(nom_ville, "artisanat")


@admin_bp.route("/villes/<nom_ville>/artisanat/<int:id>/delete", methods=["POST"])
@admin_required
def artisanat_delete(nom_ville, id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM artisanat WHERE id=%s AND nom_ville=%s",
                (id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Artisanat supprimé.", "success")
    return _detail_redirect(nom_ville, "artisanat")


# ---------------------------------------------------------------------------
# Vestimentaire CRUD (patrimoine_vestimentaire table)
# ---------------------------------------------------------------------------


def _validate_vestimentaire(form):
    nom = (form.get("nom") or "").strip()
    description = (form.get("description") or "").strip() or None
    if not nom:
        return None, None, "Le nom est requis."
    if len(nom) > 100:
        return None, None, "Le nom dépasse 100 caractères."
    return nom, description, None


@admin_bp.route("/villes/<nom_ville>/vestimentaire/new", methods=["POST"])
@admin_required
def vestimentaire_new(nom_ville):
    nom, description, err = _validate_vestimentaire(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "vestimentaire")

    slug = slugify(nom)
    image_path, upload_err = _upload_image_if_present(
        request.files.get("image"), slug, folder="vestimentaire"
    )
    if upload_err:
        flash(f"Erreur d'upload Cloudinary : {upload_err}", "error")
        return _detail_redirect(nom_ville, "vestimentaire")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO patrimoine_vestimentaire (nom_ville, nom, "
                "description, image_path) VALUES (%s, %s, %s, %s)",
                (nom_ville, nom, description, image_path),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Vêtement ajouté.", "success")
    return _detail_redirect(nom_ville, "vestimentaire")


@admin_bp.route("/villes/<nom_ville>/vestimentaire/<int:id>/edit", methods=["POST"])
@admin_required
def vestimentaire_edit(nom_ville, id):
    nom, description, err = _validate_vestimentaire(request.form)
    if err:
        flash(err, "error")
        return _detail_redirect(nom_ville, "vestimentaire")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT image_path FROM patrimoine_vestimentaire "
                "WHERE id=%s AND nom_ville=%s",
                (id, nom_ville),
            )
            current = cur.fetchone()
            if not current:
                flash("Vêtement introuvable.", "error")
                return _detail_redirect(nom_ville, "vestimentaire")

            slug = slugify(nom)
            new_image, upload_err = _upload_image_if_present(
                request.files.get("image"), slug, folder="vestimentaire"
            )
            if upload_err:
                flash(f"Erreur d'upload Cloudinary : {upload_err}", "error")
                return _detail_redirect(nom_ville, "vestimentaire")
            image_path = new_image or current["image_path"]

            cur.execute(
                "UPDATE patrimoine_vestimentaire SET nom=%s, description=%s, "
                "image_path=%s WHERE id=%s AND nom_ville=%s",
                (nom, description, image_path, id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Vêtement modifié.", "success")
    return _detail_redirect(nom_ville, "vestimentaire")


@admin_bp.route("/villes/<nom_ville>/vestimentaire/<int:id>/delete", methods=["POST"])
@admin_required
def vestimentaire_delete(nom_ville, id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM patrimoine_vestimentaire "
                "WHERE id=%s AND nom_ville=%s",
                (id, nom_ville),
            )
        conn.commit()
    finally:
        conn.close()
    flash("Vêtement supprimé.", "success")
    return _detail_redirect(nom_ville, "vestimentaire")
