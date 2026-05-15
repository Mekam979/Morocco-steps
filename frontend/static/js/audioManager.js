/**
 * AudioManager — central background-music system for Morocco Secrets.
 * Resolves a category from URL / template / localStorage, plays the matching
 * track from /static/sounds/, persists mute state and the active track across
 * navigation, and falls back to a first-interaction unlock when the browser
 * blocks autoplay (with a subtle toast on the first such block).
 */

const AudioManager = {
    audio: null,
    currentFile: null,
    fadeInterval: null,
    fadeDuration: 1000,
    defaultVolume: 0.3,
    isMuted: localStorage.getItem('ambient_music_muted') === 'true',
    started: false,                                                // current page: audio is actively playing
    confirmed: localStorage.getItem('ambient_music_started') === 'true', // user has confirmed once across nav
    _gestureArmed: false,

    AUDIO_MAP: {
        'cotieres':    'cotieres.mp3',
        'montagne':    'montagen.mp3',
        'sahariennes': 'Desert.mp3',
        'culturelles': 'cultureele.mp3',
        'agricoles':   'agricole.mp3',
        'accueil':     'accueil.mpeg',
        'default':     'accueil.mpeg',

        'côtières':           'cotieres.mp3',
        'Villes côtières':    'cotieres.mp3',
        'Villes sahariennes': 'Desert.mp3',
        'Villes de montagne': 'montagen.mp3',
        'Villes culturelles': 'cultureele.mp3',
        'Villes agricoles':   'agricole.mp3'
    },

    init() {
        this.audio = document.getElementById('background-audio');
        if (!this.audio) {
            this.audio = document.createElement('audio');
            this.audio.id = 'background-audio';
            document.body.appendChild(this.audio);
        }
        this.audio.loop = true;
        this.audio.volume = 0;

        this.createMuteButton();
        this.setupFilterClickListeners();

        const file = this.detectCategory();
        this.currentFile = file;
        if (file && !this.isMuted) {
            this.play(file);
        }
    },

    detectCategory() {
        const templateType = window.activeFilterType;
        if (templateType && this.AUDIO_MAP[templateType]) {
            const file = this.AUDIO_MAP[templateType];
            localStorage.setItem('activeCategoryAudio', file);
            return file;
        }

        const path = window.location.pathname.toLowerCase();

        const filterMatch = path.match(/\/filter\/([^/?#]+)/);
        if (filterMatch) {
            const slug = decodeURIComponent(filterMatch[1]);
            for (const key in this.AUDIO_MAP) {
                if (slug.includes(key.toLowerCase())) {
                    const file = this.AUDIO_MAP[key];
                    localStorage.setItem('activeCategoryAudio', file);
                    return file;
                }
            }
        }

        if (path === '/' || path === '/home' || path === '/index') {
            const file = this.AUDIO_MAP['default'];
            localStorage.setItem('activeCategoryAudio', file);
            return file;
        }

        const remembered = localStorage.getItem('activeCategoryAudio');
        if (remembered) return remembered;

        return this.AUDIO_MAP['default'];
    },

    play(file) {
        if (!file || !this.audio) return;
        const newSrc = `/static/sounds/${file}`;

        if (this.audio.src.endsWith(newSrc) && !this.audio.paused) {
            this.currentFile = file;
            this.markStarted();
            return;
        }

        this.currentFile = file;
        localStorage.setItem('activeCategoryAudio', file);
        localStorage.setItem('ambient_music_playing', 'true');

        this.fadeOut(() => {
            this.audio.src = newSrc;
            this._attemptPlay();
        });
    },

    _attemptPlay() {
        const p = this.audio.play();
        if (p && typeof p.then === 'function') {
            p.then(() => {
                this.markStarted();
                this.removeToast();
                this.fadeIn();
            }).catch(() => {
                if (!this.confirmed) this.showToast();
                this.armUserGesture();
            });
        } else {
            this.markStarted();
            this.fadeIn();
        }
    },

    armUserGesture() {
        if (this._gestureArmed) return;
        this._gestureArmed = true;

        const events = ['click', 'scroll', 'mousemove', 'keydown', 'touchstart'];
        const unlock = () => {
            this._gestureArmed = false;
            events.forEach(e => document.removeEventListener(e, unlock));
            this.removeToast();
            this.confirmed = true;
            localStorage.setItem('ambient_music_started', 'true');
            if (this.isMuted) return;
            const p = this.audio.play();
            if (p && typeof p.then === 'function') {
                p.then(() => { this.markStarted(); this.fadeIn(); }).catch(() => {});
            } else {
                this.markStarted();
                this.fadeIn();
            }
        };
        events.forEach(e => document.addEventListener(e, unlock, { once: true }));
    },

    markStarted() {
        this.started = true;
        this.confirmed = true;
        localStorage.setItem('ambient_music_started', 'true');
    },

    setupFilterClickListeners() {
        document.querySelectorAll('.filter-tab, .dropdown-menu a, .cat-card').forEach(link => {
            link.addEventListener('click', () => {
                const text = (link.textContent || '').trim();
                const href = link.getAttribute('href') || '';
                const key = this.matchKey(text) || this.matchKey(href);
                if (key) {
                    const file = this.AUDIO_MAP[key];
                    localStorage.setItem('activeCategoryAudio', file);
                    localStorage.setItem('ambient_music_playing', 'true');
                }
            });
        });
    },

    matchKey(s) {
        if (!s) return null;
        const lower = s.toLowerCase();
        for (const key in this.AUDIO_MAP) {
            if (key === 'default') continue;
            if (lower.includes(key.toLowerCase())) return key;
        }
        return null;
    },

    mute() {
        this.isMuted = true;
        this.started = false;
        localStorage.setItem('ambient_music_muted', 'true');
        localStorage.setItem('ambient_music_playing', 'false');
        this.fadeOut(() => this.audio && this.audio.pause());
        this.updateButtonIcon();
    },

    unmute() {
        this.isMuted = false;
        localStorage.setItem('ambient_music_muted', 'false');
        localStorage.setItem('ambient_music_playing', 'true');
        this.updateButtonIcon();
        const file = this.currentFile || this.detectCategory();
        this.play(file);
    },

    toggleMute() {
        // First click before audio has actually started — treat as start gesture,
        // do NOT toggle mute. Otherwise we'd "mute" already-paused audio and force
        // a second click to actually hear anything.
        if (!this.started) {
            this.removeToast();
            if (this.isMuted) {
                this.isMuted = false;
                localStorage.setItem('ambient_music_muted', 'false');
            }
            this.updateButtonIcon();
            const file = this.currentFile || this.detectCategory();
            if (file) this.play(file);
            return;
        }
        if (this.isMuted) this.unmute(); else this.mute();
    },

    updateButtonIcon() {
        const btn = document.getElementById('music-toggle');
        if (btn) btn.innerHTML = this.isMuted ? '🔇' : '🔊';
    },

    showToast() {
        if (document.getElementById('audio-toast')) return;
        const t = document.createElement('div');
        t.id = 'audio-toast';
        t.textContent = '🔊 Cliquez pour activer le son';
        Object.assign(t.style, {
            position: 'fixed',
            bottom: '145px',
            right: '20px',
            zIndex: '9999',
            background: 'rgba(0, 0, 0, 0.78)',
            color: '#fff',
            padding: '10px 16px',
            borderRadius: '20px',
            fontSize: '0.88rem',
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            boxShadow: '0 4px 14px rgba(0, 0, 0, 0.25)',
            backdropFilter: 'blur(6px)',
            opacity: '0',
            transition: 'opacity 0.4s ease, transform 0.4s ease',
            transform: 'translateY(8px)',
            pointerEvents: 'none'
        });
        document.body.appendChild(t);
        requestAnimationFrame(() => {
            t.style.opacity = '1';
            t.style.transform = 'translateY(0)';
        });
    },

    removeToast() {
        const t = document.getElementById('audio-toast');
        if (!t) return;
        t.style.opacity = '0';
        t.style.transform = 'translateY(8px)';
        setTimeout(() => t.remove(), 400);
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
        if (!this.audio || this.audio.paused || this.audio.volume === 0) {
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

window.AudioManager = AudioManager;

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => AudioManager.init());
} else {
    AudioManager.init();
}
