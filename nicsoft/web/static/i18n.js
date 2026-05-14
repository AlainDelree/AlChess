/**
 * AlChess i18n — module de traduction
 *
 * Usage :
 *   t("menu.btn.pedagogique")               → chaîne traduite
 *   t("error.ouverture_introuvable", {id})  → avec interpolation
 *
 * Le DOM est mis à jour via les attributs :
 *   data-i18n             → textContent
 *   data-i18n-html        → innerHTML (pour les clés contenant du HTML)
 *   data-i18n-placeholder → placeholder
 *   data-i18n-title       → title
 */

const SUPPORTED_LOCALES = ['fr', 'en'];
const DEFAULT_LOCALE    = 'fr';

/** Sauvegarde la locale dans localStorage ET un cookie persistant (1 an). */
function _saveLang(locale) {
  localStorage.setItem('alchess_locale', locale);
  document.cookie = `alchess_locale=${locale};max-age=${365*24*3600};path=/`;
}

/** Lit la locale depuis le cookie d'abord (plus fiable), localStorage en fallback. */
function _loadLang() {
  const m = document.cookie.match(/(?:^|; )alchess_locale=([^;]*)/);
  if (m && SUPPORTED_LOCALES.includes(m[1])) return m[1];
  return localStorage.getItem('alchess_locale');
}

const i18n = (() => {
  let _data   = {};
  let _locale = DEFAULT_LOCALE;

  /** Charge un fichier JSON de traduction et applique au DOM. */
  async function load(locale) {
    if (!SUPPORTED_LOCALES.includes(locale)) locale = DEFAULT_LOCALE;
    try {
      const res = await fetch(`/static/i18n/${locale}.json?v=${Date.now()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      _data   = await res.json();
      _locale = locale;
      _saveLang(locale);
      applyToDOM();
      _updateSelector(locale);
      // Resynchronise les éléments dynamiques après chaque chargement de locale
      if (typeof window._refreshDynamicLabels === 'function') window._refreshDynamicLabels();
    } catch (e) {
      console.warn(`[i18n] Impossible de charger ${locale}.json :`, e);
    }
  }

  /** Retourne une Promise qui se résout dès que _data est chargé pour la locale actuelle. */
  function ready() { return window.i18nReady || Promise.resolve(); }

  /**
   * Traduit une clé avec interpolation optionnelle.
   * Si la clé est absente, retourne la clé elle-même (visible = bug à corriger).
   */
  function t(key, vars = {}) {
    let str = Object.prototype.hasOwnProperty.call(_data, key) ? _data[key] : key;
    Object.entries(vars).forEach(([k, v]) => {
      str = str.replaceAll(`{${k}}`, v);
    });
    return str;
  }

  /** Applique les traductions à tous les éléments data-i18n* du DOM. */
  function applyToDOM() {
    // Met à jour lang sur <html> → le date picker Chrome suit la locale
    document.documentElement.lang = _locale === 'en' ? 'en-GB' : 'fr-FR';
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.dataset.i18n;
      // Ne remplace que le premier nœud texte direct (préserve les enfants HTML)
      const textNode = Array.from(el.childNodes).find(n => n.nodeType === Node.TEXT_NODE);
      if (textNode) {
        textNode.textContent = t(key);
      } else {
        el.textContent = t(key);
      }
    });
    document.querySelectorAll('[data-i18n-html]').forEach(el => {
      el.innerHTML = t(el.dataset.i18nHtml);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
      el.title = t(el.dataset.i18nTitle);
    });
  }

  /** Locale courante. */
  function locale() { return _locale; }

  /** Met à jour le sélecteur HTML si présent. */
  function _updateSelector(locale) {
    const sel = document.getElementById('lang-selector');
    if (sel) sel.value = locale;
  }

  return { load, t, applyToDOM, locale, ready };
})();

/** Raccourci global utilisé dans app.js et le HTML inline. */
function t(key, vars) { return i18n.t(key, vars); }

/** Initialisation au chargement de la page. */
(function _initI18n() {
  const saved = _loadLang() || DEFAULT_LOCALE;
  window.i18nReady = i18n.load(saved);
})();

/** Surcharge load() pour que window.i18nReady pointe toujours vers le chargement en cours.
 *  La locale est sauvegardée immédiatement (avant le fetch) pour éviter la perte de préférence
 *  si la page est fermée avant la fin du chargement. */
const _origLoad = i18n.load.bind(i18n);
i18n.load = function(locale) {
  if (SUPPORTED_LOCALES.includes(locale)) {
    _saveLang(locale);  // sauvegarde immédiate dans localStorage + cookie
  }
  window.i18nReady = _origLoad(locale);
  return window.i18nReady;
};
