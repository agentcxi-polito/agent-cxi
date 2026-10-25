import json
import os
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="Agent CXI – Prevendita B2B", page_icon="🔎", layout="wide")

BASE = Path(__file__).parent
ISTRUZIONI = (BASE / "istruzioni.txt").read_text(encoding="utf-8")
VERSIONE = "v0"
HAS_SECRETS = st.secrets.load_if_toml_exists()
API_KEY = (st.secrets.get("GEMINI_API_KEY") if HAS_SECRETS else None) or os.environ.get("GEMINI_API_KEY")
MODELLO = (st.secrets.get("GEMINI_MODEL") if HAS_SECRETS else None) or os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"
DEMO = not API_KEY

DEMO_RIEPILOGO = """| Parametro | Valore |
| --- | --- |
| Settore o attività | (esempio) |
| Area geografica | (esempio) |
| Dimensione | (esempio) |
| Numero di nomi | 5 |
| Criteri di priorità | non indicato: modello di default CXI |

Confermi questi parametri?"""

DEMO_OUTPUT = """**MODALITÀ DEMO: risposta di esempio, non generata dall'agent e non basata su dati reali.**

**Tabella 1 – New names**

| Azienda | Sede | Dimensione | Altri dati chiave | Fonte |
| --- | --- | --- | --- | --- |
| Esempio Uno S.p.A. | Città A | 1,2 milioni di clienti (2025) | Dato di esempio | Fonte di esempio (A) |
| Esempio Due S.r.l. | Città B | 600.000 clienti (2025) | Dato di esempio | Fonte di esempio (A) |

**Tabella 2 – Clusterizzazione e priorità**

| Priorità | Azienda | Cluster | Cambiamento | Accessibilità | Volume | Totale |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Esempio Due S.r.l. | Regionale in crescita | 3 | 3 | 2 | 8 |
| 2 | Esempio Uno S.p.A. | Grande operatore | 2 | 1 | 3 | 6 |

**Verifiche consigliate:** in modalità demo non ci sono dati da verificare."""


def client():
    return genai.Client(api_key=API_KEY)


def richiesta(dati):
    righe = [
        "Nuova richiesta di prevendita.",
        "",
        "Obbligatori",
        f"- Settore o attività: {dati['settore']}",
        f"- Area geografica (sede): {dati['area']}",
        f"- Dimensione, metrica e soglia: {dati['dimensione']}",
        f"- Numero di nomi: almeno {dati['nomi']}",
        "",
        "Facoltativi",
        f"- Criteri di priorità: {dati['priorita'] or 'non indicati (usa il modello di default)'}",
        f"- Criteri qualitativi: {dati['qualitativi'] or 'non indicati'}",
        f"- Tema del progetto da proporre: {dati['tema'] or 'non indicato'}",
        f"- Aziende da escludere: {dati['esclusioni'] or 'nessuna'}",
    ]
    if dati["libero"]:
        righe += ["", f"Testo libero: {dati['libero']}"]
    return "\n".join(righe)


def chiama(storia):
    risposta = client().models.generate_content(
        model=MODELLO,
        contents=storia,
        config=types.GenerateContentConfig(
            system_instruction=ISTRUZIONI,
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.2,
        ),
    )
    fonti, ricerche = [], []
    cand = risposta.candidates[0] if risposta.candidates else None
    meta = cand.grounding_metadata if cand else None
    if meta:
        ricerche = list(meta.web_search_queries or [])
        fonti = [{"titolo": c.web.title, "link": c.web.uri} for c in (meta.grounding_chunks or []) if c.web]
    return risposta.text or "", fonti, ricerche


def msg(ruolo, testo):
    return types.Content(role=ruolo, parts=[types.Part(text=testo)])


def reset():
    for k in ["fase", "storia", "riepilogo", "output", "fonti", "ricerche", "dati", "tempo", "inizio"]:
        st.session_state.pop(k, None)


st.session_state.setdefault("fase", "input")

with st.sidebar:
    st.header("Agent CXI · beta")
    st.write("Assistente alla prevendita B2B per i Customer Account di CXI.")
    st.markdown(
        "**Come funziona**\n\n"
        "1. Descrivi il target.\n"
        "2. Controlla il riepilogo dei parametri.\n"
        "3. Conferma: l'agent cerca sul web e restituisce le cinque tabelle con le fonti.\n"
        "4. Verifica i dati segnalati prima di usarli."
    )
    st.caption(f"Modello: {MODELLO} · Istruzioni: {VERSIONE}")
    if DEMO:
        st.warning("Modalità demo: manca la chiave API. Le risposte sono esempi fissi.")
    st.download_button("Scarica le istruzioni dell'agent", ISTRUZIONI, file_name=f"istruzioni_{VERSIONE}.txt")
    st.caption("Non inserire informazioni riservate di CXI o dei suoi clienti.")

st.title("Ricerca prospect B2B")

if st.session_state.fase == "input":
    with st.form("richiesta"):
        st.subheader("Il target")
        c1, c2 = st.columns(2)
        settore = c1.text_area("Settore o attività *", placeholder="es. aziende che vendono luce e gas a famiglie e piccole imprese")
        area = c2.text_input("Area geografica della sede *", placeholder="es. Nord Italia; Piemonte o Lombardia")
        dimensione = c2.text_input("Dimensione: metrica e soglia *", placeholder="es. almeno 500.000 clienti; fatturato > 300 mln €")
        nomi = c2.number_input("Numero minimo di nomi *", min_value=1, max_value=15, value=5)
        with st.expander("Criteri facoltativi"):
            priorita = st.text_input("Criteri di priorità", placeholder="vuoto = modello di default CXI (cambiamento, accessibilità, volume)")
            qualitativi = st.text_input("Criteri qualitativi", placeholder="es. gestiscono grandi volumi di contatti con i clienti")
            tema = st.text_input("Tema del progetto da proporre", placeholder="es. BDC e gestione dei lead")
            esclusioni = st.text_input("Aziende da escludere", placeholder="es. clienti attuali di CXI")
            libero = st.text_area("Altro (testo libero)")
        inviato = st.form_submit_button("1 · Controlla i parametri", type="primary")
    if inviato:
        if not (settore.strip() and area.strip() and dimensione.strip()):
            st.warning("Compila settore, area e dimensione.")
        else:
            dati = dict(settore=settore.strip(), area=area.strip(), dimensione=dimensione.strip(), nomi=int(nomi),
                        priorita=priorita.strip(), qualitativi=qualitativi.strip(), tema=tema.strip(),
                        esclusioni=esclusioni.strip(), libero=libero.strip())
            testo = richiesta(dati) + "\n\nEsegui solo il passo 0: riepiloga i parametri in una tabella, poi fermati e chiedi conferma."
            st.session_state.inizio = time.perf_counter()
            with st.spinner("Controllo dei parametri…"):
                riepilogo = DEMO_RIEPILOGO if DEMO else chiama([msg("user", testo)])[0]
            st.session_state.update(dati=dati, storia=[("user", testo), ("model", riepilogo)], riepilogo=riepilogo, fase="conferma")
            st.rerun()

elif st.session_state.fase == "conferma":
    st.subheader("Riepilogo dei parametri")
    st.markdown(st.session_state.riepilogo)
    correzioni = st.text_area("Correzioni (facoltative)", placeholder="es. la soglia è sul fatturato, non sui dipendenti")
    c1, c2 = st.columns(2)
    if c1.button("2 · Conferma e avvia la ricerca", type="primary"):
        testo = "Parametri confermati." + (f" Correzioni dell'account: {correzioni.strip()}" if correzioni.strip() else "") + \
                " Procedi con i passi da 1 a 5 e restituisci l'output nel formato della sezione 6."
        storia = st.session_state.storia + [("user", testo)]
        with st.spinner("Ricerca sul web e analisi in corso: può richiedere qualche minuto…"):
            output, fonti, ricerche = (DEMO_OUTPUT, [], []) if DEMO else chiama([msg(r, t) for r, t in storia])
        st.session_state.update(storia=storia + [("model", output)], output=output, fonti=fonti, ricerche=ricerche,
                                tempo=time.perf_counter() - st.session_state.inizio, fase="output")
        st.rerun()
    if c2.button("Modifica la richiesta"):
        reset()
        st.rerun()

else:
    st.markdown(st.session_state.output)
    st.caption(f"Tempo dalla richiesta all'output: {st.session_state.tempo / 60:.1f} minuti (verifica esclusa).")
    with st.expander(f"Fonti consultate dall'agent ({len(st.session_state.fonti)})"):
        for f in st.session_state.fonti:
            st.markdown(f"- [{f['titolo']}]({f['link']})")
        if st.session_state.ricerche:
            st.caption("Ricerche eseguite: " + " · ".join(st.session_state.ricerche))
    ora = datetime.now().strftime("%Y-%m-%d_%H-%M")
    log = dict(data=ora, modello=MODELLO, istruzioni=VERSIONE, input=st.session_state.dati,
               conversazione=[{"ruolo": r, "testo": t} for r, t in st.session_state.storia],
               fonti=st.session_state.fonti, ricerche=st.session_state.ricerche,
               minuti=round(st.session_state.tempo / 60, 2), demo=DEMO)
    c1, c2, c3 = st.columns(3)
    c1.download_button("Scarica l'output (.md)", st.session_state.output, file_name=f"output_{ora}.md")
    c2.download_button("Scarica il registro completo (.json)", json.dumps(log, ensure_ascii=False, indent=2), file_name=f"registro_{ora}.json")
    if c3.button("Nuova richiesta", type="primary"):
        reset()
        st.rerun()
