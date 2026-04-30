class Slideshow {
    constructor(containerId, items, interval = 4000) {
        this.container = document.getElementById(containerId);
        this.items = items;
        this.index = 0;
        this.interval = interval;

        if (!this.container) {
            console.error("Container not found:", containerId);
            return;
        }

        if (!items || items.length === 0) {
            this.container.innerHTML = "<p>Aucun contenu disponible</p>";
            return;
        }

        this.init();
    }

    init() {
        this.render();
        this.startAutoSlide();
    }

    render() {
        this.container.innerHTML = `
            <div class="slideshow">
                <button class="prev">&#10094;</button>

                <div class="slide">
                    <img src="${this.items[this.index].image}" class="slide-image">
                    <div class="slide-caption">
                        <h3>${this.items[this.index].title}</h3>
                        <p>${this.items[this.index].description}</p>
                    </div>
                </div>

                <button class="next">&#10095;</button>
            </div>
        `;

        this.addEvents();
    }

    updateSlide() {
        const slide = this.container.querySelector(".slide");
        const item = this.items[this.index];

        slide.innerHTML = `
            <img src="${item.image}" class="slide-image">
            <div class="slide-caption">
                <h3>${item.title}</h3>
                <p>${item.description}</p>
            </div>
        `;
    }

    nextSlide() {
        this.index = (this.index + 1) % this.items.length;
        this.updateSlide();
    }

    prevSlide() {
        this.index = (this.index - 1 + this.items.length) % this.items.length;
        this.updateSlide();
    }

    startAutoSlide() {
        this.timer = setInterval(() => {
            this.nextSlide();
        }, this.interval);
    }

    stopAutoSlide() {
        clearInterval(this.timer);
    }

    addEvents() {
        const nextBtn = this.container.querySelector(".next");
        const prevBtn = this.container.querySelector(".prev");

        nextBtn.addEventListener("click", () => {
            this.stopAutoSlide();
            this.nextSlide();
            this.startAutoSlide();
        });

        prevBtn.addEventListener("click", () => {
            this.stopAutoSlide();
            this.prevSlide();
            this.startAutoSlide();
        });

        // Pause au survol (UX PRO 🔥)
        this.container.addEventListener("mouseenter", () => this.stopAutoSlide());
        this.container.addEventListener("mouseleave", () => this.startAutoSlide());
    }
}