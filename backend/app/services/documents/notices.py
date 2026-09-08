"""Consistent output notices; the bundled terms govern their legal context."""
from app.core.languages import pick

OUTPUT_NOTICES = {'nl': 'CONCEPT — EMCargo. Controleer, vul aan en laat waar vereist bevoegd ondertekenen vóór gebruik. DG-vrijgave is een interne controle. Zie gebruikersvoorwaarden (TERMS.nl.md). Softwarelicentie: Apache License 2.0 met Commons Clause.', 'en': 'DRAFT — EMCargo. Verify, complete and obtain an authorised signature where required before use. DG release is an internal review. See terms of use (TERMS.nl.md). Software licence: Apache License 2.0 with Commons Clause.', 'de': 'ENTWURF — EMCargo. Vor Verwendung prüfen, ergänzen und bei Bedarf befugt unterzeichnen lassen. DG-Freigabe ist eine interne Prüfung. Siehe Nutzungsbedingungen (TERMS.nl.md). Softwarelizenz: Apache License 2.0 mit Commons Clause.', 'fr': 'PROJET — EMCargo. Vérifiez, complétez et faites signer si nécessaire avant utilisation. La validation DG est un contrôle interne. Voir les conditions d’utilisation (TERMS.nl.md). Licence : Apache License 2.0 avec Commons Clause.'}

def output_notice(language: str) -> str:
    return pick(OUTPUT_NOTICES, language)
