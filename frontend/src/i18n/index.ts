import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import nl from "./nl.json";
import en from "./en.json";
import de from "./de.json";
import fr from "./fr.json";
import { DEFAULT_LANGUAGE, documentLanguage } from "./language";

i18n.use(initReactI18next).init({
  resources: {
    nl: { translation: nl },
    en: { translation: en },
    de: { translation: de },
    fr: { translation: fr },
  },
  // A stored language we do not (or no longer) know must not leave the
  // interface empty; documentLanguage falls back to Dutch in that case.
  lng: documentLanguage(localStorage.getItem("emcargo-lang") || DEFAULT_LANGUAGE),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export default i18n;
