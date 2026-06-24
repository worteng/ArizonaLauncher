/* =========================================================
   Arizona Launcher by Halfik — main.js
   Smooth-scroll, reveal, бургер-меню, FAQ-аккордеон,
   активный пункт навигации, glass-эффект шапки.
   ========================================================= */
(function () {
    'use strict';

    /* ── Glass-эффект шапки при скролле ── */
    var header = document.getElementById('header');
    function onScrollHeader() {
        if (window.scrollY > 24) header.classList.add('scrolled');
        else header.classList.remove('scrolled');
    }
    window.addEventListener('scroll', onScrollHeader, { passive: true });
    onScrollHeader();

    /* ── Бургер-меню (мобильное) ── */
    var burger = document.getElementById('burger');
    var mobileMenu = document.getElementById('mobileMenu');
    function setMenu(open) {
        mobileMenu.classList.toggle('open', open);
        burger.setAttribute('aria-expanded', open ? 'true' : 'false');
        // Меняем иконку menu <-> x
        burger.innerHTML = open
            ? '<i data-lucide="x"></i>'
            : '<i data-lucide="menu"></i>';
        if (window.lucide) lucide.createIcons({ nameAttr: 'data-lucide' });
        document.body.style.overflow = open ? 'hidden' : '';
    }
    if (burger && mobileMenu) {
        burger.addEventListener('click', function () {
            setMenu(!mobileMenu.classList.contains('open'));
        });
        // Закрытие по клику на пункт меню
        mobileMenu.querySelectorAll('a').forEach(function (a) {
            a.addEventListener('click', function () { setMenu(false); });
        });
        // Закрытие по Escape
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && mobileMenu.classList.contains('open')) setMenu(false);
        });
    }

    /* ── Smooth-scroll по якорям (с учётом фиксированной шапки) ── */
    var navLinks = Array.from(document.querySelectorAll('.nav a[href^="#"], .mobile-menu a[href^="#"]'));
    document.querySelectorAll('a[href^="#"]').forEach(function (link) {
        link.addEventListener('click', function (e) {
            var id = link.getAttribute('href');
            if (!id || id === '#') return;
            var target = document.querySelector(id);
            if (!target) return;
            e.preventDefault();
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    });

    /* ── Активный пункт навигации при скролле (scroll spy) ── */
    var sections = ['features', 'install', 'news', 'faq']
        .map(function (id) { return document.getElementById(id); })
        .filter(Boolean);
    var spyLinks = Array.from(document.querySelectorAll('.nav a'));

    if ('IntersectionObserver' in window && sections.length) {
        var spy = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    var id = entry.target.id;
                    spyLinks.forEach(function (l) {
                        l.classList.toggle('active', l.getAttribute('href') === '#' + id);
                    });
                }
            });
        }, { rootMargin: '-45% 0px -50% 0px', threshold: 0 });
        sections.forEach(function (s) { spy.observe(s); });
    }

    /* ── Reveal-анимация секций ── */
    var reveals = document.querySelectorAll('.reveal');
    if ('IntersectionObserver' in window) {
        var revObserver = new IntersectionObserver(function (entries, obs) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('in');
                    obs.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
        reveals.forEach(function (el) { revObserver.observe(el); });
    } else {
        reveals.forEach(function (el) { el.classList.add('in'); });
    }

    /* ── FAQ-аккордеон ── */
    document.querySelectorAll('.faq-item').forEach(function (item) {
        var btn = item.querySelector('.faq-q');
        var ans = item.querySelector('.faq-a');
        if (!btn || !ans) return;
        btn.addEventListener('click', function () {
            var isOpen = item.classList.contains('open');
            // Закрываем все остальные
            document.querySelectorAll('.faq-item.open').forEach(function (other) {
                if (other !== item) {
                    other.classList.remove('open');
                    other.querySelector('.faq-q').setAttribute('aria-expanded', 'false');
                    other.querySelector('.faq-a').style.maxHeight = null;
                }
            });
            item.classList.toggle('open', !isOpen);
            btn.setAttribute('aria-expanded', String(!isOpen));
            if (!isOpen) {
                ans.style.maxHeight = ans.scrollHeight + 'px';
            } else {
                ans.style.maxHeight = null;
            }
        });
    });

    // Пересчёт высоты открытых FAQ при ресайзе
    var resizeTimer;
    window.addEventListener('resize', function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            document.querySelectorAll('.faq-item.open .faq-a').forEach(function (ans) {
                ans.style.maxHeight = ans.scrollHeight + 'px';
            });
        }, 150);
    });
})();
