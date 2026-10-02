
// ===== Theme =====
(function() {
  var saved = localStorage.getItem('claude-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  updateThemeIcons(saved);
})();

function toggleTheme() {
  var current = document.documentElement.getAttribute('data-theme');
  var next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('claude-theme', next);
  updateThemeIcons(next);
}

function updateThemeIcons(theme) {
  var moon = document.querySelector('.icon-moon');
  var sun = document.querySelector('.icon-sun');
  if (!moon || !sun) return;
  if (theme === 'dark') { moon.style.display = ''; sun.style.display = 'none'; }
  else { moon.style.display = 'none'; sun.style.display = ''; }
}

// ===== Language (i18n) =====
(function() {
  var saved = localStorage.getItem('claude-lang') || 'ru';
  applyLang(saved, false);
})();

function setLang(lang) {
  localStorage.setItem('claude-lang', lang);
  applyLang(lang, true);
}

function applyLang(lang, animate) {
  // Show/hide inline spans
  document.querySelectorAll('[data-lang]').forEach(function(el) {
    if (el.getAttribute('data-lang') === lang) {
      el.classList.add('lang-visible');
    } else {
      el.classList.remove('lang-visible');
    }
  });
  // Show/hide block elements
  document.querySelectorAll('[data-lang-block]').forEach(function(el) {
    if (el.getAttribute('data-lang-block') === lang) {
      el.classList.add('lang-visible');
    } else {
      el.classList.remove('lang-visible');
    }
  });
  // Translate option elements that have data-ru / data-en attributes
  document.querySelectorAll('option[data-ru]').forEach(function(el) {
    var t = el.getAttribute('data-' + lang);
    if (t) el.textContent = t;
  });
  // Translate search input placeholder
  document.querySelectorAll('input[data-placeholder-ru]').forEach(function(el) {
    var t = el.getAttribute('data-placeholder-' + lang);
    if (t) el.placeholder = t;
  });
  // Toggle button states
  var btnRu = document.getElementById('langRu');
  var btnEn = document.getElementById('langEn');
  if (btnRu) btnRu.classList.toggle('active', lang === 'ru');
  if (btnEn) btnEn.classList.toggle('active', lang === 'en');
  // Update sync status text if on index
  updateSyncStatus();
  // Update filter count label
  var label = document.getElementById('countLabel');
  if (label && label.textContent) filterConvs();
}

// ===== Copy code =====
function copyCode(btn) {
  var pre = btn.closest('.code-block').querySelector('pre');
  var text = pre ? pre.innerText : '';
  navigator.clipboard.writeText(text).then(function() {
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(function() { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 1500);
  }).catch(function() {
    btn.textContent = 'Error';
    setTimeout(function() { btn.textContent = 'Copy'; }, 1500);
  });
}

// ===== Scroll FABs =====
function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function scrollToBottom() {
  window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
}

function updateScrollFabs() {
  var fabTop = document.getElementById('fabTop');
  var fabBottom = document.getElementById('fabBottom');
  if (!fabTop || !fabBottom) return;
  var scrolled = window.scrollY;
  var maxScroll = document.body.scrollHeight - window.innerHeight;
  // Show "top" button after scrolling down 200px
  fabTop.classList.toggle('hidden', scrolled < 200);
  // Hide "bottom" button when within 100px of the bottom
  fabBottom.classList.toggle('hidden', maxScroll > 0 && scrolled >= maxScroll - 100);
}

// ===== Mapping (localStorage) =====
var MAPPING_KEY = 'claude-mapping';

function loadBrowserMapping() {
  try { return JSON.parse(localStorage.getItem(MAPPING_KEY) || '{}'); }
  catch(e) { return {}; }
}

function saveBrowserMapping(m) {
  localStorage.setItem(MAPPING_KEY, JSON.stringify(m));
}

function assignProject(convUuid, projUuid) {
  var m = loadBrowserMapping();
  if (projUuid) {
    m[convUuid] = projUuid;
  } else {
    delete m[convUuid];
  }
  saveBrowserMapping(m);
  // Update the "Open project" link in topbar
  var link = document.getElementById('assignProjLink');
  if (link) {
    if (projUuid) {
      link.href = '../projects/' + projUuid + '/index.html';
      link.style.display = '';
    } else {
      link.style.display = 'none';
    }
  }
}

function exportMapping() {
  var m = loadBrowserMapping();
  var json = JSON.stringify(m, null, 2);
  var blob = new Blob([json], { type: 'application/json' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'mapping.json';
  a.click();
  URL.revokeObjectURL(a.href);
}

function clearBrowserMapping() {
  var lang = localStorage.getItem('claude-lang') || 'ru';
  var msg = lang === 'en'
    ? 'Reset all browser mapping? (mapping.json on disk will not change)'
    : 'Сбросить весь браузерный маппинг? (mapping.json на диске не изменится)';
  if (confirm(msg)) {
    localStorage.removeItem(MAPPING_KEY);
    updateSyncStatus();
  }
}

function updateSyncStatus() {
  var el = document.getElementById('syncStatus');
  if (!el) return;
  var m = loadBrowserMapping();
  var cnt = Object.keys(m).length;
  var lang = localStorage.getItem('claude-lang') || 'ru';
  if (lang === 'en') {
    el.textContent = cnt > 0 ? cnt + ' mappings in browser (not saved)' : 'No unsaved mappings';
  } else {
    el.textContent = cnt > 0 ? cnt + ' привязок в браузере (не сохранено)' : 'Нет несохранённых привязок';
  }
}

// ===== Filter & search (all_conversations page) =====
function filterConvs() {
  var q = (document.getElementById('searchInput') || { value: '' }).value.toLowerCase();
  var proj = (document.getElementById('projFilter') || { value: '' }).value;
  var sort = (document.getElementById('sortSelect') || { value: 'updated' }).value;

  var cards = Array.from(document.querySelectorAll('.conv-card'));
  var visible = [];

  cards.forEach(function(card) {
    var name = (card.dataset.name || '');
    var preview = (card.dataset.preview || '');
    var cardProj = (card.dataset.proj || '');
    var matchQ = !q || name.includes(q) || preview.includes(q);
    var matchP = !proj || (proj === '__none__' ? !cardProj : cardProj === proj);
    var show = matchQ && matchP;
    card.style.display = show ? '' : 'none';
    if (show) visible.push(card);
  });

  // Sort
  var grid = document.getElementById('convGrid');
  if (grid) {
    visible.sort(function(a, b) {
      if (sort === 'msgs') return parseInt(b.dataset.msgs || 0) - parseInt(a.dataset.msgs || 0);
      if (sort === 'created') return (b.dataset.created || '').localeCompare(a.dataset.created || '');
      return (b.dataset.updated || '').localeCompare(a.dataset.updated || '');
    });
    visible.forEach(function(c) { grid.appendChild(c); });
  }

  var lang = localStorage.getItem('claude-lang') || 'ru';
  var label = document.getElementById('countLabel');
  if (label) {
    label.textContent = lang === 'en'
      ? visible.length + ' of ' + cards.length
      : visible.length + ' из ' + cards.length;
  }
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', function() {
  // Re-apply theme icons (DOM now ready)
  var savedTheme = localStorage.getItem('claude-theme') || 'dark';
  updateThemeIcons(savedTheme);

  // Apply language
  var savedLang = localStorage.getItem('claude-lang') || 'ru';
  applyLang(savedLang, false);

  if (window.PAGE_TYPE === 'all_convs') {
    filterConvs();
  }
  if (document.getElementById('syncPanel')) {
    updateSyncStatus();
  }
  if (window.PAGE_TYPE === 'conversation') {
    window.addEventListener('scroll', updateScrollFabs, { passive: true });
    updateScrollFabs();
  }
});
