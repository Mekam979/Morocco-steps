/**
 * Ambient Music Manager for Morocco Secrets
 * Handles background music with transitions and persistence.
 */

const AmbientMusic = {
    audio: null,
    currentType: null,
    isMuted: localStorage.getItem('ambient_music_muted') === 'true',
    fadeDuration: 1000,
    defaultVolume: 0.4,

    typeToMusic: {
        'accueil': 'accueil.mpeg',
        'côtières': 'cotieres.mp3',
        'cotieres': 'cotieres.mp3',
        'sahariennes': 'Desert.mp3',
        'montagne': 'montagen.mp3',
        'culturelles': 'cultureele.mp3',
        'agricoles': 'agricole.mp3',
        'Villes côtières': 'cotieres.mp3',
        'Villes sahariennes': 'Desert.mp3',
        'Villes de montagne': 'montagen.mp3',
        'Villes culturelles': 'cultureele.mp3',
        'Villes agricoles': 'agricole.mp3'
    },

    init() {
        if (!this.audio) {
            this.audio = new Audio();
            this.audio.loop = true;
            this.audio.volume = 0;
        }

        this.createMuteButton();
        this.checkCurrentPage();
        this.setupListeners();
    },

    createMuteButton() {
        if (document.getElementById('music-toggle')) return;

        const btn = document.createElement('button');
        btn.id = 'music-toggle';
        btn.className = 'music-toggle-btn';
        btn.innerHTML = this.isMuted ? '🔇' : '🔊';
        btn.title = "Musique d'ambiance";

        Object.assign(btn.style, {
            position: 'fixed',
            bottom: '90px',
            right: '20px',
            zIndex: '9998',
            background: 'rgba(107, 29, 29, 0.85)',
            color: 'white',
            border: '1px solid rgba(255, 255, 255, 0.3)',
            borderRadius: '50%',
            width: '45px',
            height: '45px',
            fontSize: '20px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'all 0.3s ease',
            boxShadow: '0 4px 15px rgba(0,0,0,0.2)',
            backdropFilter: 'blur(5px)'
        });

        btn.addEventListener('mouseenter', () => {
            btn.style.transform = 'scale(1.1)';
            btn.style.background = 'rgba(107, 29, 29, 1)';
        });

        btn.addEventListener('mouseleave', () => {
            btn.style.transform = 'scale(1)';
            btn.style.background = 'rgba(107, 29, 29, 0.85)';
        });

        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleMute();
        });

        document.body.appendChild(btn);
    },

    setupListeners() {
        document.querySelectorAll('.filter-tab, .dropdown-menu a, .cat-card').forEach(link => {
            link.addEventListener('click', () => {
                const text = link.textContent.trim();
                const type = this.getTypeFromText(text) || this.getTypeFromHref(link.getAttribute('href'));

                if (type) {
                    this.currentType = type;
                    localStorage.setItem('ambient_music_requested_type', type);
                    localStorage.setItem('ambient_music_playing', 'true');
                }
            });
        });

        // Au premier clic sur la page, démarrer la musique
        const handleFirstInteraction = () => {
            if (localStorage.getItem('ambient_music_playing') === 'true' && !this.isMuted) {
                this.playForCurrentType();
            }
            document.removeEventListener('click', handleFirstInteraction);
        };
        document.addEventListener('click', handleFirstInteraction);

        // Arrêt propre lors du départ de la page
        window.addEventListener('beforeunload', () => {
            this.fadeOut(() => this.audio.pause());
        });
    },

    getTypeFromText(text) {
        for (const type in this.typeToMusic) {
            if (text.toLowerCase().includes(type.toLowerCase())) return type;
        }
        return null;
    },

    getTypeFromHref(href) {
        if (!href) return null;
        for (const type in this.typeToMusic) {
            if (href.toLowerCase().includes(type.toLowerCase())) return type;
        }
        return null;
    },

    checkCurrentPage() {
        const activeFilter = window.activeFilterType || '';

        // Page d'accueil — préparer la musique pour le premier clic
        if (activeFilter === 'accueil') {
            this.currentType = 'accueil';
            localStorage.setItem('ambient_music_requested_type', 'accueil');
            localStorage.setItem('ambient_music_playing', 'true');
            if (!this.isMuted) {
                this.playForCurrentType();
            }
            return;
        }

        // Autres pages (villes filtrées)
        if (activeFilter) {
            const type = this.getTypeFromText(activeFilter);
            if (type) {
                this.currentType = type;
                if (localStorage.getItem('ambient_music_playing') === 'true' && !this.isMuted) {
                    this.playForCurrentType();
                }
            }
        }
    },

    playForCurrentType() {
        const type = this.currentType || localStorage.getItem('ambient_music_requested_type');
        if (!type || !this.typeToMusic[type]) return;

        const filename = this.typeToMusic[type];
        const newSrc = `/static/sounds/${filename}`;

        if (this.audio.src.endsWith(newSrc) && !this.audio.paused) return;

        this.fadeOut(() => {
            this.audio.src = newSrc;
            this.audio.play()
                .then(() => this.fadeIn())
                .catch(() => console.log('Autoplay bloqué — en attente d\'interaction'));
        });
    },

    toggleMute() {
        this.isMuted = !this.isMuted;
        localStorage.setItem('ambient_music_muted', this.isMuted);

        const btn = document.getElementById('music-toggle');
        if (btn) btn.innerHTML = this.isMuted ? '🔇' : '🔊';

        if (this.isMuted) {
            this.fadeOut(() => this.audio.pause());
            localStorage.setItem('ambient_music_playing', 'false');
        } else {
            localStorage.setItem('ambient_music_playing', 'true');
            this.playForCurrentType();
        }
    },

    fadeIn() {
        clearInterval(this.fadeInterval);
        let vol = 0;
        this.audio.volume = 0;
        const step = 0.05;
        const interval = this.fadeDuration / (this.defaultVolume / step);

        this.fadeInterval = setInterval(() => {
            vol += step;
            if (vol >= this.defaultVolume) {
                this.audio.volume = this.defaultVolume;
                clearInterval(this.fadeInterval);
            } else {
                this.audio.volume = vol;
            }
        }, interval);
    },

    fadeOut(callback) {
        clearInterval(this.fadeInterval);

        if (this.audio.paused || this.audio.volume === 0) {
            if (callback) callback();
            return;
        }

        let vol = this.audio.volume;
        const step = 0.05;
        const interval = this.fadeDuration / (vol / step);

        this.fadeInterval = setInterval(() => {
            vol -= step;
            if (vol <= 0) {
                this.audio.volume = 0;
                clearInterval(this.fadeInterval);
                if (callback) callback();
            } else {
                this.audio.volume = vol;
            }
        }, interval);
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => AmbientMusic.init());
} else {
    AmbientMusic.init();
}