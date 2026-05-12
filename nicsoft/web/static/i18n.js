/**
 * AlChess i18n — module de traduction
 *
 * Usage :
 *   t("menu.btn.pedagogique")               → chaîne traduite
 *   t("error.ouverture_introuvable", {id})  → avec interpolation
 *
 * Le DOM est mis à jour via les attributs :
 *   data-i18n             → textContent
 *   data-i18n-placeholder → placeholder
 *   data-i18n-title       → title
 */

const SUPPORTED_LOCALES = ['fr', 'en'];
const DEFAULT_LOCALE    = 'fr';

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
      localStorage.setItem('alchess_locale', locale);
      applyToDOM();
      _updateSelector(locale);
    } catch (e) {
      console.warn(`[i18n] Impossible de charger ${locale}.json :`, e);
    }
  }

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

  return { load, t, applyToDOM, locale };
})();

/** Raccourci global utilisé dans app.js et le HTML inline. */
function t(key, vars) { return i18n.t(key, vars); }

/** Initialisation au chargement de la page. */
(function _initI18n() {
  const saved = localStorage.getItem('alchess_locale') || DEFAULT_LOCALE;
  window.i18nReady = i18n.load(saved);
})();
