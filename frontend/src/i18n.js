// Bilingual chrome, in a dictionary rather than a framework.
//
// Scope is deliberate and stated on the Trust page: the navigation, the Trust
// page and the morning brief (whose sentences live in backend/brief.py and come
// back already translated from /api/brief?lang=hi). Deep prose on the other tabs
// stays English — a half-translated dashboard reads like a bug, a clearly scoped
// bilingual shell does not.
//
// Two rules keep this honest:
//   * `t()` never returns a raw key: an unknown language or key falls back to
//     English, so a missing string degrades instead of showing "tab.trust";
//   * localStorage is touched only inside try/catch, exactly like theme.js, so a
//     private window cannot break the page.
import { useCallback, useEffect, useState } from 'react'

export const LANGS = [
  { id: 'en', label: 'EN' },
  { id: 'hi', label: 'हिं' },
]

const STRINGS = {
  en: {
    'tab.dashboard': 'Dashboard',
    'tab.ward': 'Wards',
    'tab.trend': 'Trend',
    'tab.anomalies': 'Anomalies',
    'tab.disagreements': 'Disagreements',
    'tab.complaints': 'Complaints',
    'tab.leaderboard': 'Leaderboard',
    'tab.simulator': 'Simulator',
    'tab.brief': 'Briefing',
    'tab.trust': 'Trust',
    'tab.ingest': 'Ingest',
    'tab.benchmark': 'Benchmark',

    'topbar.home': '← Home',
    'topbar.homeTitle': 'Back to the landing page',
    'topbar.search': 'Search',
    'topbar.searchTitle': 'Search everything (Ctrl/Cmd-K)',
    'topbar.theme': 'theme',
    'topbar.themeTitle': 'Switch between the dark and light palettes',
    'topbar.language': 'Language',
    'offline.badge': 'offline — last cached view',

    'export.csv': 'Export CSV',
    'export.empty': 'nothing to export yet',

    'trust.title': 'Can I trust this number?',
    'trust.intro': 'Every figure in this dashboard is a count from a query. This page shows how much of the raw data survived to be counted, and which file produced each endpoint.',
    'trust.readings': 'Readings counted',
    'trust.complete': 'Complete',
    'trust.lab': 'Lab-verified',
    'trust.unusable': 'No result',
    'trust.age': 'Newest reading',
    'trust.days': 'days old',
    'trust.byParam': 'By parameter',
    'trust.param': 'Parameter',
    'trust.band': 'Band',
    'trust.findings': 'Findings',
    'trust.worst': 'Worst cells this month',
    'trust.lineage': 'Where every number comes from',
    'trust.lineageIntro': 'One row per read endpoint. Open it for the exact SQL, or copy the command that runs the same file.',
    'trust.endpoint': 'Endpoint',
    'trust.step': 'SQL step',
    'trust.tables': 'Tables read',
    'trust.note': 'What it answers',
    'trust.showSql': 'Show the SQL',
    'trust.copyCmd': 'Copy command',
    'trust.copied': 'copied',
    'trust.take': 'Take it with you',
    'trust.takeIntro': 'Everything below is generated from the same queries — nothing is uploaded anywhere, and no account is involved.',
    'trust.ics': 'Breach calendar (.ics)',
    'trust.icsNote': 'One all-day event per parameter projected to cross its limit, with a 7-day alarm.',
    'trust.atom': 'Copy Atom feed URL',
    'trust.atomNote': 'The morning brief as a feed, so a reader can subscribe without an account.',
    'trust.cache': 'Clear cached data',
    'trust.clear': 'Clear cached data',
    'trust.cacheCleared': 'cache cleared — reloading',
    'trust.cacheNote': 'The service worker keeps the last successful API responses so the dashboard opens offline. Clear it if a number looks stale.',
    'trust.mockNote': 'Mock mode: the calendar and feed are served by the API, so the links are shown but not downloadable.',
    'trust.scope': 'Bilingual scope: navigation, this page and the morning brief. Data prose on the other tabs stays in English.',

    'brief.language': 'Brief language',
    'brief.copy': 'Copy markdown',
    'brief.download': 'Download .md',
    'brief.downloadCsv': 'Download .csv (actions)',
  },

  hi: {
    'tab.dashboard': 'डैशबोर्ड',
    'tab.ward': 'वार्ड',
    'tab.trend': 'रुझान',
    'tab.anomalies': 'विसंगतियाँ',
    'tab.disagreements': 'सेंसर बनाम लैब',
    'tab.complaints': 'शिकायतें',
    'tab.leaderboard': 'प्राथमिकता सूची',
    'tab.simulator': 'परिदृश्य',
    'tab.brief': 'सुबह की रिपोर्ट',
    'tab.trust': 'भरोसा',
    'tab.ingest': 'डेटा लाएँ',
    'tab.benchmark': 'गति माप',

    'topbar.home': '← होम',
    'topbar.homeTitle': 'लैंडिंग पेज पर लौटें',
    'topbar.search': 'खोजें',
    'topbar.searchTitle': 'सब कुछ खोजें (Ctrl/Cmd-K)',
    'topbar.theme': 'थीम',
    'topbar.themeTitle': 'डार्क और लाइट रंग बदलें',
    'topbar.language': 'भाषा',
    'offline.badge': 'ऑफ़लाइन — अंतिम सहेजा दृश्य',

    'export.csv': 'CSV डाउनलोड',
    'export.empty': 'अभी निर्यात के लिए कुछ नहीं',

    'trust.title': 'क्या इन आँकड़ों पर भरोसा करें?',
    'trust.intro': 'इस डैशबोर्ड का हर आँकड़ा किसी क्वेरी की गिनती है। यह पेज दिखाता है कि कच्चे डेटा का कितना हिस्सा गिनने लायक बचा, और कौन-सी फ़ाइल किस endpoint से जुड़ी है।',
    'trust.readings': 'गिनी गई रीडिंग',
    'trust.complete': 'पूर्ण',
    'trust.lab': 'लैब-पुष्ट',
    'trust.unusable': 'परिणाम नहीं',
    'trust.age': 'नवीनतम रीडिंग',
    'trust.days': 'दिन पुरानी',
    'trust.byParam': 'पैरामीटर के अनुसार',
    'trust.param': 'पैरामीटर',
    'trust.band': 'श्रेणी',
    'trust.findings': 'निष्कर्ष',
    'trust.worst': 'इस महीने की सबसे कमज़ोर कोशिकाएँ',
    'trust.lineage': 'हर आँकड़ा कहाँ से आता है',
    'trust.lineageIntro': 'हर read endpoint की एक पंक्ति। खोलें और ठीक वही SQL देखें, या उसे चलाने वाला कमांड कॉपी करें।',
    'trust.endpoint': 'एंडपॉइंट',
    'trust.step': 'SQL चरण',
    'trust.tables': 'पढ़ी गई तालिकाएँ',
    'trust.note': 'क्या उत्तर देता है',
    'trust.showSql': 'SQL दिखाएँ',
    'trust.copyCmd': 'कमांड कॉपी करें',
    'trust.copied': 'कॉपी हो गया',
    'trust.take': 'अपने साथ ले जाएँ',
    'trust.takeIntro': 'नीचे सब कुछ उन्हीं क्वेरी से बनता है — कुछ भी कहीं अपलोड नहीं होता और किसी खाते की ज़रूरत नहीं।',
    'trust.ics': 'उल्लंघन कैलेंडर (.ics)',
    'trust.icsNote': 'हर ऐसे पैरामीटर के लिए एक पूरे दिन का इवेंट जो सीमा पार करने वाला है, 7 दिन पहले अलार्म के साथ।',
    'trust.atom': 'Atom फ़ीड URL कॉपी करें',
    'trust.atomNote': 'सुबह की रिपोर्ट फ़ीड के रूप में, ताकि कोई भी बिना खाते के सब्सक्राइब कर सके।',
    'trust.cache': 'कैश साफ़ करें',
    'trust.clear': 'कैश साफ़ करें',
    'trust.cacheCleared': 'कैश साफ़ हुआ — पेज फिर खुल रहा है',
    'trust.cacheNote': 'सर्विस वर्कर अंतिम सफल API उत्तर सहेजता है ताकि डैशबोर्ड ऑफ़लाइन खुले। कोई आँकड़ा पुराना लगे तो कैश साफ़ करें।',
    'trust.mockNote': 'मॉक मोड: कैलेंडर और फ़ीड API देता है, इसलिए लिंक दिखते हैं पर डाउनलोड नहीं होते।',
    'trust.scope': 'द्विभाषी दायरा: नेविगेशन, यह पेज और सुबह की रिपोर्ट। बाकी टैब का डेटा टेक्स्ट अंग्रेज़ी में रहता है।',

    'brief.language': 'रिपोर्ट की भाषा',
    'brief.copy': 'मार्कडाउन कॉपी करें',
    'brief.download': '.md डाउनलोड करें',
    'brief.downloadCsv': '.csv (काम) डाउनलोड करें',
  },
}

export const DEFAULT_LANG = 'en'
const KEY = 'wardq.lang'

function stored() {
  try {
    const value = window.localStorage.getItem(KEY)
    if (STRINGS[value]) return value
  } catch {
    /* storage unavailable — fall through to the default */
  }
  return DEFAULT_LANG
}

export function t(lang, key, vars) {
  const table = STRINGS[lang] || STRINGS[DEFAULT_LANG]
  const fallback = STRINGS[DEFAULT_LANG]
  let text = table[key] || fallback[key] || key
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.split(`{${name}}`).join(String(value))
    }
  }
  return text
}

export function useLang() {
  const [lang, setLang] = useState(stored)

  useEffect(() => {
    try {
      window.localStorage.setItem(KEY, lang)
    } catch {
      /* still applied for this session, just not remembered */
    }
    document.documentElement.lang = lang
  }, [lang])

  const pick = useCallback((next) => {
    setLang(STRINGS[next] ? next : DEFAULT_LANG)
  }, [])

  return [lang, pick]
}
