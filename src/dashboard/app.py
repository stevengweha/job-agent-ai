# src/dashboard/app.py

import sys
from pathlib import Path
from datetime import datetime, timedelta

root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

import streamlit as st
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from src.database import SessionLocal, JobModel, ApplicationModel
import pandas as pd
import numpy as np
import altair as alt

# Import sécurisé pour le visualiseur DOCX
try:
    import docx
except ImportError:
    docx = None

# Import de ta chat interface dédiée depuis ton module dashboard
try:
    from src.dashboard.chat_interface import render_chat_tab
except ImportError:
    def render_chat_tab():
        st.error("⚠️ Le module `src.dashboard.chat_interface` est introuvable. Vérifie son chemin d'accès.")

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Job Agent AI • Executive Control Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- PALETTE COULEURS COHÉRENTE (utilisée partout : KPI, charts, badges) ---
STATUS_COLORS = {
    "NEW":              "#94a3b8",
    "PENDING_APPROVAL":  "#f59e0b",
    "CV_READY":          "#3b82f6",
    "APPLIED":           "#22c55e",
    "REJECTED":          "#ef4444",
}
ACCENT = "#2563eb"
ACCENT_2 = "#7c3aed"
ACCENT_3 = "#0ea5e9"

# --- DESIGN & STYLING CSS ADAPTATIF ---
st.markdown(f"""
    <style>
    .stApp {{
        background-color: var(--background-color);
        color: var(--text-color);
    }}

    /* Transition plus douce du contenu principal quand la sidebar se
       plie/déplie : réduit le risque de flash de contenu non stylé pendant
       le recalcul de layout de Streamlit. */
    section[data-testid="stSidebar"] {{
        transition: width 0.2s ease, min-width 0.2s ease;
    }}
    div[data-testid="stAppViewContainer"] > .main {{
        transition: max-width 0.2s ease, padding 0.2s ease;
    }}

    /* ---- Metrics ---- */
    div[data-testid="stMetric"] {{
        background: linear-gradient(160deg, var(--secondary-background-color) 0%, var(--secondary-background-color) 100%);
        padding: 18px 16px !important;
        border-radius: 14px !important;
        border: 1px solid rgba(128, 128, 128, 0.15) !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.05) !important;
        transition: transform 0.15s ease;
    }}
    div[data-testid="stMetric"]:hover {{
        transform: translateY(-2px);
        border-color: rgba(37, 99, 235, 0.35) !important;
    }}
    div[data-testid="stMetric"] label {{
        font-weight: 700 !important;
        font-size: 10.5px !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        opacity: 0.75;
    }}
    div[data-testid="stMetricValue"] {{
        font-size: 26px !important;
        font-weight: 800 !important;
    }}

    /* ---- Hero banner ---- */
    .hero-banner {{
        padding: 26px 28px;
        background: linear-gradient(120deg, rgba(37,99,235,0.12), rgba(124,58,237,0.08));
        border-left: 5px solid {ACCENT};
        border-radius: 14px;
        margin-bottom: 26px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.06);
    }}
    .hero-title {{ font-size: 26px; font-weight: 800; margin: 0; }}
    .hero-subtitle {{ font-size: 13.5px; margin-top: 6px; margin-bottom: 0; opacity: 0.75; }}

    /* ---- Section headers ---- */
    .section-header {{
        font-size: 15px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin: 28px 0 12px 0;
        padding-bottom: 8px;
        border-bottom: 2px solid rgba(128,128,128,0.15);
        opacity: 0.9;
    }}

    /* ---- Buttons ---- */
    .stButton button {{
        border-radius: 8px !important;
        font-weight: 600 !important;
    }}

    /* ---- Status badges ---- */
    .badge {{
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 700;
        color: white;
        letter-spacing: 0.02em;
    }}

    /* ---- Insight cards ---- */
    .insight-card {{
        background-color: var(--secondary-background-color);
        border-radius: 12px;
        padding: 16px 18px;
        border: 1px solid rgba(128,128,128,0.15);
        height: 100%;
    }}
    .insight-card .big {{
        font-size: 22px;
        font-weight: 800;
    }}
    .insight-card .lbl {{
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        opacity: 0.7;
        font-weight: 700;
    }}

    /* ---- KPI cards "maison" (remplace st.metric) ----
       st.metric() s'appuie sur des balises internes Streamlit dont la mise en
       page est recalculée quand la sidebar se plie/déplie ; le temps que le
       CSS se réapplique, le label + la valeur bruts peuvent brièvement
       s'afficher sans style. Ces cartes 100% HTML/CSS ne dépendent d'aucune
       structure interne de Streamlit et ne peuvent donc pas "flasher". */
    .kpi-card {{
        background: linear-gradient(160deg, var(--secondary-background-color) 0%, var(--secondary-background-color) 100%);
        padding: 16px 16px !important;
        border-radius: 14px !important;
        border: 1px solid rgba(128, 128, 128, 0.15) !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.05) !important;
        transition: transform 0.15s ease;
        min-height: 96px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 4px;
    }}
    .kpi-card:hover {{
        transform: translateY(-2px);
        border-color: rgba(37, 99, 235, 0.35) !important;
    }}
    .kpi-label {{
        font-weight: 700;
        font-size: 10.5px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        opacity: 0.7;
        line-height: 1.3;
    }}
    .kpi-value {{
        font-size: 26px;
        font-weight: 800;
        line-height: 1.15;
    }}
    .kpi-delta {{
        font-size: 12px;
        font-weight: 700;
    }}
    .kpi-delta.up {{ color: #22c55e; }}
    .kpi-delta.down {{ color: #ef4444; }}
    </style>
""", unsafe_allow_html=True)

def status_badge(status: str) -> str:
    color = STATUS_COLORS.get(status, "#94a3b8")
    return f'<span class="badge" style="background-color:{color};">{status}</span>'

def kpi_card(label: str, value, delta: str | None = None, delta_positive: bool = True, help_text: str | None = None) -> str:
    """Construit une carte KPI 100% HTML (remplace st.metric pour éviter le
    flash de texte non stylé lors du repli/dépli de la sidebar)."""
    delta_html = ""
    if delta:
        arrow_class = "up" if delta_positive else "down"
        delta_html = f'<div class="kpi-delta {arrow_class}">{delta}</div>'
    title_attr = f' title="{help_text}"' if help_text else ""
    return f"""
    <div class="kpi-card"{title_attr}>
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {delta_html}
    </div>
    """

def render_kpi_row(cols, items):
    """Affiche une rangée de KPI cards robustes dans les colonnes fournies.
    items = liste de dicts: {label, value, delta?, delta_positive?, help?}"""
    for col, item in zip(cols, items):
        with col:
            st.markdown(
                kpi_card(
                    item["label"],
                    item["value"],
                    delta=item.get("delta"),
                    delta_positive=item.get("delta_positive", True),
                    help_text=item.get("help"),
                ),
                unsafe_allow_html=True,
            )

# --- FONCTION UTILITAIRE : APERÇU DOCX ---
def get_docx_preview(file_path):
    """Extrait et formate le texte d'un fichier .docx pour l'aperçu Streamlit"""
    if not docx:
        return "⚠️ Le module `python-docx` n'est pas installé."
    try:
        doc = docx.Document(file_path)
        content_lines = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                if para.style.name.startswith('Heading') or (len(text) < 50 and text.isupper()):
                    content_lines.append(f"### {text}")
                else:
                    content_lines.append(text)
        return "\n\n".join(content_lines)
    except Exception as e:
        return f"⚠️ Impossible de charger l'aperçu du CV : {str(e)}"

# --- CONNEXION DB (lecture seule, aucune modification du schéma) ---
try:
    db: Session = SessionLocal()
    jobs = db.query(JobModel).all()
    applications = db.query(ApplicationModel).all()
    db.close()
except Exception as e:
    st.error(f"Erreur critique de connexion à la base de données : {str(e)}")
    jobs, applications = [], []

# --- BARRE LATÉRALE ---
with st.sidebar:
    st.markdown("### ⚡ Job Agent AI")
    st.caption("SUPINFO • Data Engineering & IA")

    st.divider()

    selected_tab = st.radio(
        "Navigation",
        [
            "📊 Tableau de Bord",
            "📈 Analytics Avancées",
            "📋 Pipeline & HITL",
            "📄 Traçabilité CVs",
            "💬 Chat avec l'Agent",
            "🗄️ Base de Données"
        ],
        index=0
    )

    st.divider()
    st.markdown("### 🎛️ Contrôles Agents")
    if st.button("🔄 Rafraîchir les données", use_container_width=True):
        st.rerun()

    st.markdown("---")
    st.caption("● Agent Actif • LangGraph & Groq")

# --- JOINTURE JOBS & APPLICATIONS (source unique de vérité pour tout le dashboard) ---
data_rows = []
for j in jobs:
    app = next((a for a in applications if a.job_id == j.id), None)
    data_rows.append({
        "id": j.id,
        "external_id": j.external_id,
        "platform": getattr(j, 'platform', 'linkedin') or 'linkedin',
        "title": getattr(j, 'title', 'Inconnu') or 'Inconnu',
        "company": getattr(j, 'company', 'Inconnue') or 'Inconnue',
        "contract_type": getattr(j, 'contract_type', 'Alternance') or 'Alternance',
        "location": getattr(j, 'location', 'Île-de-France') or 'Île-de-France',
        "description_url": getattr(j, 'description_url', '#'),
        "raw_description": getattr(j, 'raw_description', '') or '',
        "status": getattr(j, 'status', 'NEW') or 'NEW',
        "created_at": getattr(j, 'created_at', None),
        "ats_score": float(getattr(app, 'ats_score', 0)) if app and getattr(app, 'ats_score', None) is not None else 0.0,
        "missing_skills": getattr(app, 'missing_skills', []) if app and getattr(app, 'missing_skills', None) else [],
        "tailored_cv_path": getattr(app, 'tailored_cv_path', None) if app else None,
        "audit_trail": getattr(app, 'audit_trail', []) if app and getattr(app, 'audit_trail', None) else [],
        "applied_at": getattr(app, 'applied_at', None) if app else None,
        "updated_at": getattr(app, 'updated_at', None) if app else None,
    })

df = pd.DataFrame(data_rows)

# Normalisation des dates pour analyses temporelles
if not df.empty:
    for col in ["created_at", "applied_at", "updated_at"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")

# ==========================================
# TAB 1 : TABLEAU DE BORD & KPIS STRATÉGIQUES
# ==========================================
if selected_tab == "📊 Tableau de Bord":
    st.markdown("""
        <div class="hero-banner">
            <p class="hero-title">⚡ Centre de Contrôle Exécutif & Analytique</p>
            <p class="hero-subtitle">Supervision avancée et pilotage stratégique de la recherche d'alternance Data Engineering & IA.</p>
        </div>
    """, unsafe_allow_html=True)

    if df.empty:
        st.warning("⚠️ Aucune donnée enregistrée pour le moment. Lance ton agent pour alimenter le dashboard.")
    else:
        total_offers = len(df)
        applied_count = len(df[df['status'] == "APPLIED"])
        pending_count = len(df[df['status'] == "PENDING_APPROVAL"])
        rejected_count = len(df[df['status'] == "REJECTED"])
        cv_ready_count = len(df[df['status'] == "CV_READY"])
        new_count = len(df[df['status'] == "NEW"])
        qualified_offers = total_offers - rejected_count

        avg_score = df['ats_score'].mean() if total_offers > 0 else 0
        max_score = df['ats_score'].max() if total_offers > 0 else 0
        high_fit_count = len(df[df['ats_score'] >= 75])

        conversion_rate = (applied_count / total_offers) * 100 if total_offers > 0 else 0
        automation_rate = (applied_count / qualified_offers) * 100 if qualified_offers > 0 else 0
        rejection_rate = (rejected_count / total_offers) * 100 if total_offers > 0 else 0
        cv_generated_count = df['tailored_cv_path'].dropna().nunique()

        all_missing = [skill for skills_list in df['missing_skills'].dropna() for skill in skills_list]
        top_missing_skill = pd.Series(all_missing).mode()[0] if all_missing else "Aucune"

        # Vélocité : offres captées ces 7 derniers jours
        if df['created_at'].notna().any():
            last_7d = df[df['created_at'] >= (pd.Timestamp.now() - pd.Timedelta(days=7))]
            velocity_7d = len(last_7d)
        else:
            velocity_7d = None

        # Temps moyen jusqu'à candidature
        applied_df = df[(df['applied_at'].notna()) & (df['created_at'].notna())]
        if not applied_df.empty:
            avg_days_to_apply = (applied_df['applied_at'] - applied_df['created_at']).dt.total_seconds().mean() / 86400
        else:
            avg_days_to_apply = None

        # --- BANDEAU D'INSIGHTS RAPIDES ---
        st.markdown('<div class="section-header">🚀 Insights Clés</div>', unsafe_allow_html=True)
        i1, i2, i3, i4 = st.columns(4)
        with i1:
            st.markdown(f"""<div class="insight-card"><div class="lbl">Pipeline Sain</div>
                <div class="big" style="color:{'#22c55e' if conversion_rate>=15 else '#f59e0b'}">{conversion_rate:.0f}%</div>
                <div style="font-size:12px;opacity:0.7;">de conversion offre → candidature</div></div>""", unsafe_allow_html=True)
        with i2:
            vel_txt = f"{velocity_7d}" if velocity_7d is not None else "N/A"
            st.markdown(f"""<div class="insight-card"><div class="lbl">Vélocité Agent</div>
                <div class="big" style="color:{ACCENT_3}">{vel_txt}</div>
                <div style="font-size:12px;opacity:0.7;">offres captées / 7 jours</div></div>""", unsafe_allow_html=True)
        with i3:
            days_txt = f"{avg_days_to_apply:.1f}j" if avg_days_to_apply is not None else "N/A"
            st.markdown(f"""<div class="insight-card"><div class="lbl">Réactivité</div>
                <div class="big" style="color:{ACCENT_2}">{days_txt}</div>
                <div style="font-size:12px;opacity:0.7;">délai moyen offre → candidature</div></div>""", unsafe_allow_html=True)
        with i4:
            st.markdown(f"""<div class="insight-card"><div class="lbl">Qualité Ciblage</div>
                <div class="big" style="color:{'#22c55e' if high_fit_count/total_offers>=0.3 else '#f59e0b'}">{high_fit_count}/{total_offers}</div>
                <div style="font-size:12px;opacity:0.7;">offres à haute compatibilité (≥75%)</div></div>""", unsafe_allow_html=True)

        # --- SECTION 1 : VOLUMÉTRIE & STATUTS ---
        st.markdown('<div class="section-header">📌 Volumétrie & Flux Opérationnel</div>', unsafe_allow_html=True)
        render_kpi_row(
            st.columns(5),
            [
                {"label": "Total Offres Aspirées", "value": total_offers, "help": "Nombre total d'annonces enregistrées dans la base"},
                {"label": "Nouvelles", "value": new_count, "help": "Offres pas encore traitées par l'agent"},
                {"label": "En Attente (HITL)", "value": pending_count, "help": "Offres nécessitant une validation humaine"},
                {"label": "Candidatures Envoyées", "value": applied_count, "help": "Postulations confirmées"},
                {"label": "Offres Rejetées", "value": rejected_count, "delta": f"-{rejection_rate:.0f}%", "delta_positive": False, "help": "Offres écartées par l'agent ou manuellement"},
            ],
        )

        # --- SECTION 2 : PERFORMANCE ATS & QUALITÉ ---
        st.markdown('<div class="section-header">🎯 Performance ATS & Alignement Profil</div>', unsafe_allow_html=True)
        render_kpi_row(
            st.columns(4),
            [
                {"label": "Score ATS Moyen", "value": f"{avg_score:.0f}%", "help": "Pertinence moyenne par rapport au Master CV"},
                {"label": "Score ATS Max", "value": f"{max_score:.0f}%", "help": "Meilleure correspondance d'offre enregistrée"},
                {"label": "High Fit (≥ 75%)", "value": high_fit_count, "help": "Nombre d'offres hautement compatibles"},
                {"label": "Top Lacune ATS", "value": top_missing_skill, "help": "Compétence manquante la plus fréquente"},
            ],
        )

        # --- SECTION 3 : CONVERSION & AUTOMATISATION ---
        st.markdown('<div class="section-header">⚡ Efficacité du Pipeline</div>', unsafe_allow_html=True)
        render_kpi_row(
            st.columns(3),
            [
                {"label": "Taux de Conversion Global", "value": f"{conversion_rate:.0f}%", "help": "Candidatures / Total offres"},
                {"label": "Taux d'Automatisation", "value": f"{automation_rate:.0f}%", "help": "Part des offres qualifiées traitées avec succès"},
                {"label": "CVs Sur-mesure Générés", "value": cv_generated_count, "help": "Documents Word prêts à l'emploi"},
            ],
        )

        st.divider()

        # --- GRAPHIQUES AVANCÉS (ALTAIR) ---
        st.markdown('<div class="section-header">📈 Analyses Visuelles Détaillées</div>', unsafe_allow_html=True)

        color_scale_status = alt.Scale(domain=list(STATUS_COLORS.keys()), range=list(STATUS_COLORS.values()))

        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.markdown("#### Répartition des Statuts du Pipeline")
            status_df = df['status'].value_counts().reset_index()
            status_df.columns = ['Statut', 'Nombre']
            chart_status = alt.Chart(status_df).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
                x=alt.X('Statut:N', sort='-y', title='Statut'),
                y=alt.Y('Nombre:Q', title="Nombre d'offres"),
                color=alt.Color('Statut:N', scale=color_scale_status, legend=None),
                tooltip=['Statut', 'Nombre']
            ).properties(height=300)
            st.altair_chart(chart_status, use_container_width=True)

        with col_g2:
            st.markdown("#### Top 5 Entreprises Ciblées")
            company_df = df['company'].value_counts().head(5).reset_index()
            company_df.columns = ['Entreprise', 'Nombre']
            chart_company = alt.Chart(company_df).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, color=ACCENT).encode(
                x=alt.X('Entreprise:N', sort='-y', title='Entreprise'),
                y=alt.Y('Nombre:Q', title='Offres ciblées'),
                tooltip=['Entreprise', 'Nombre']
            ).properties(height=300)
            st.altair_chart(chart_company, use_container_width=True)

        col_g3, col_g4 = st.columns(2)

        with col_g3:
            st.markdown("#### Distribution des Scores ATS")
            chart_ats = alt.Chart(df).mark_bar(opacity=0.85, binSpacing=2, color=ACCENT_2).encode(
                alt.X("ats_score:Q", bin=alt.Bin(maxbins=10), title="Tranche de Score ATS (%)"),
                alt.Y("count()", title="Nombre d'offres"),
                tooltip=[alt.Tooltip("count()", title="Nombre d'offres")]
            ).properties(height=300)
            st.altair_chart(chart_ats, use_container_width=True)

        with col_g4:
            st.markdown("#### Répartition par Plateforme")
            if 'platform' in df.columns:
                plat_df = df['platform'].value_counts().reset_index()
                plat_df.columns = ['Plateforme', 'Nombre']
                chart_plat = alt.Chart(plat_df).mark_arc(innerRadius=55).encode(
                    theta=alt.Theta(field="Nombre", type="quantitative"),
                    color=alt.Color(field="Plateforme", type="nominal"),
                    tooltip=['Plateforme', 'Nombre']
                ).properties(height=300)
                st.altair_chart(chart_plat, use_container_width=True)

        # --- FUNNEL DE CONVERSION ---
        st.markdown("#### 🎯 Funnel de Conversion du Pipeline")
        funnel_order = ["NEW", "CV_READY", "PENDING_APPROVAL", "APPLIED"]
        funnel_counts = []
        for s in funnel_order:
            funnel_counts.append({"Étape": s, "Nombre": len(df[df['status'].isin(
                funnel_order[funnel_order.index(s):] if s != "APPLIED" else ["APPLIED"]
            )]) if s == "NEW" else len(df[df['status'] == s])})
        # Funnel simplifié et cohérent : cumul décroissant basé sur l'avancement réel
        stage_map = {"NEW": 0, "CV_READY": 1, "PENDING_APPROVAL": 2, "APPLIED": 3}
        df_active = df[df['status'] != "REJECTED"].copy()
        funnel_rows = []
        for stage_name, stage_rank in stage_map.items():
            count_reached = len(df_active[df_active['status'].map(lambda s: stage_map.get(s, -1)) >= stage_rank])
            funnel_rows.append({"Étape": stage_name, "Offres ayant atteint l'étape": count_reached})
        funnel_df = pd.DataFrame(funnel_rows)
        chart_funnel = alt.Chart(funnel_df).mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6).encode(
            y=alt.Y('Étape:N', sort=list(stage_map.keys()), title=None),
            x=alt.X("Offres ayant atteint l'étape:Q", title="Nombre d'offres"),
            color=alt.Color('Étape:N', scale=color_scale_status, legend=None),
            tooltip=['Étape', "Offres ayant atteint l'étape"]
        ).properties(height=220)
        st.altair_chart(chart_funnel, use_container_width=True)
        st.caption("ℹ️ Le funnel exclut les offres rejetées et suit la progression cumulée réelle du pipeline (NEW → CV_READY → PENDING_APPROVAL → APPLIED).")

# ==========================================
# TAB 2 : ANALYTICS AVANCÉES
# ==========================================
elif selected_tab == "📈 Analytics Avancées":
    st.markdown("""
        <div class="hero-banner">
            <p class="hero-title">📈 Analytics Avancées & Tendances</p>
            <p class="hero-subtitle">Vision fine de la dynamique temporelle, des compétences et de la performance par segment.</p>
        </div>
    """, unsafe_allow_html=True)

    if df.empty:
        st.warning("⚠️ Aucune donnée disponible pour l'analyse avancée.")
    else:
        color_scale_status = alt.Scale(domain=list(STATUS_COLORS.keys()), range=list(STATUS_COLORS.values()))

        # --- TIMELINE D'ACQUISITION ---
        st.markdown('<div class="section-header">🕒 Timeline d\'Acquisition des Offres</div>', unsafe_allow_html=True)
        if df['created_at'].notna().any():
            ts_df = df.dropna(subset=['created_at']).copy()
            ts_df['date'] = ts_df['created_at'].dt.date
            daily_counts = ts_df.groupby(['date', 'status']).size().reset_index(name='Nombre')
            chart_ts = alt.Chart(daily_counts).mark_area(opacity=0.75, interpolate='monotone').encode(
                x=alt.X('date:T', title='Date'),
                y=alt.Y('Nombre:Q', stack='zero', title="Nombre d'offres"),
                color=alt.Color('status:N', scale=color_scale_status, title='Statut'),
                tooltip=['date:T', 'status', 'Nombre']
            ).properties(height=300)
            st.altair_chart(chart_ts, use_container_width=True)
        else:
            st.info("Pas de données temporelles (`created_at`) disponibles pour tracer la timeline.")

        col_a1, col_a2 = st.columns(2)

        with col_a1:
            st.markdown('<div class="section-header">🧩 Compétences Manquantes les Plus Fréquentes</div>', unsafe_allow_html=True)
            all_missing = [skill for skills_list in df['missing_skills'].dropna() for skill in skills_list]
            if all_missing:
                skills_df = pd.Series(all_missing).value_counts().head(10).reset_index()
                skills_df.columns = ['Compétence', 'Occurrences']
                chart_skills = alt.Chart(skills_df).mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6, color=ACCENT_2).encode(
                    y=alt.Y('Compétence:N', sort='-x', title=None),
                    x=alt.X('Occurrences:Q'),
                    tooltip=['Compétence', 'Occurrences']
                ).properties(height=320)
                st.altair_chart(chart_skills, use_container_width=True)
                st.caption("💡 Ces compétences reviennent le plus souvent comme lacunes par rapport au Master CV : pistes de montée en compétences prioritaires.")
            else:
                st.info("Aucune compétence manquante enregistrée.")

        with col_a2:
            st.markdown('<div class="section-header">🏢 Score ATS Moyen par Entreprise (Top 10)</div>', unsafe_allow_html=True)
            comp_score = df.groupby('company')['ats_score'].agg(['mean', 'count']).reset_index()
            comp_score.columns = ['Entreprise', 'Score Moyen', 'Nb Offres']
            comp_score = comp_score.sort_values('Score Moyen', ascending=False).head(10)
            chart_comp_score = alt.Chart(comp_score).mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6).encode(
                y=alt.Y('Entreprise:N', sort='-x', title=None),
                x=alt.X('Score Moyen:Q', title='Score ATS moyen (%)'),
                color=alt.Color('Score Moyen:Q', scale=alt.Scale(scheme='blues'), legend=None),
                tooltip=['Entreprise', alt.Tooltip('Score Moyen:Q', format='.1f'), 'Nb Offres']
            ).properties(height=320)
            st.altair_chart(chart_comp_score, use_container_width=True)

        st.divider()

        col_a3, col_a4 = st.columns(2)
        with col_a3:
            st.markdown('<div class="section-header">📄 Type de Contrat</div>', unsafe_allow_html=True)
            contract_df = df['contract_type'].value_counts().reset_index()
            contract_df.columns = ['Contrat', 'Nombre']
            chart_contract = alt.Chart(contract_df).mark_arc(innerRadius=55).encode(
                theta=alt.Theta(field='Nombre', type='quantitative'),
                color=alt.Color(field='Contrat', type='nominal', scale=alt.Scale(scheme='tealblues')),
                tooltip=['Contrat', 'Nombre']
            ).properties(height=280)
            st.altair_chart(chart_contract, use_container_width=True)

        with col_a4:
            st.markdown('<div class="section-header">📍 Localisation des Offres</div>', unsafe_allow_html=True)
            loc_df = df['location'].value_counts().head(8).reset_index()
            loc_df.columns = ['Localisation', 'Nombre']
            chart_loc = alt.Chart(loc_df).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, color=ACCENT_3).encode(
                x=alt.X('Localisation:N', sort='-y'),
                y=alt.Y('Nombre:Q'),
                tooltip=['Localisation', 'Nombre']
            ).properties(height=280)
            st.altair_chart(chart_loc, use_container_width=True)

        st.divider()

        # --- HEATMAP STATUT x PLATEFORME ---
        st.markdown('<div class="section-header">🔥 Heatmap : Statut × Plateforme</div>', unsafe_allow_html=True)
        heat_df = df.groupby(['platform', 'status']).size().reset_index(name='Nombre')
        chart_heat = alt.Chart(heat_df).mark_rect().encode(
            x=alt.X('status:N', title='Statut', sort=list(STATUS_COLORS.keys())),
            y=alt.Y('platform:N', title='Plateforme'),
            color=alt.Color('Nombre:Q', scale=alt.Scale(scheme='blues'), title="Nombre d'offres"),
            tooltip=['platform', 'status', 'Nombre']
        ).properties(height=220)
        st.altair_chart(chart_heat, use_container_width=True)

        # --- SCATTER SCORE ATS vs NOMBRE DE LACUNES ---
        st.markdown('<div class="section-header">🎯 Score ATS vs Nombre de Compétences Manquantes</div>', unsafe_allow_html=True)
        scatter_df = df.copy()
        scatter_df['nb_missing'] = scatter_df['missing_skills'].apply(lambda x: len(x) if isinstance(x, list) else 0)
        chart_scatter = alt.Chart(scatter_df).mark_circle(size=90, opacity=0.7).encode(
            x=alt.X('nb_missing:Q', title='Nombre de compétences manquantes'),
            y=alt.Y('ats_score:Q', title='Score ATS (%)'),
            color=alt.Color('status:N', scale=color_scale_status, title='Statut'),
            tooltip=['company', 'title', 'ats_score', 'nb_missing', 'status']
        ).properties(height=320).interactive()
        st.altair_chart(chart_scatter, use_container_width=True)
        st.caption("💡 Une corrélation négative attendue : plus de lacunes ⇒ score ATS plus faible. Les points isolés méritent une revue manuelle.")

# ==========================================
# TAB 3 : PIPELINE & PILOTAGE HITL
# ==========================================
elif selected_tab == "📋 Pipeline & HITL":
    st.markdown("""
        <div class="hero-banner">
            <p class="hero-title">📋 Gestion du Pipeline & Validation Humaine</p>
            <p class="hero-subtitle">Filtre, inspecte et prends le contrôle des décisions autonomes de l'agent.</p>
        </div>
    """, unsafe_allow_html=True)

    col_f1, col_f2, col_f3, col_f4 = st.columns([1, 1, 1, 1])
    with col_f1:
        status_filter = st.selectbox("Filtrer par Statut :", ["TOUS", "PENDING_APPROVAL", "CV_READY", "APPLIED", "REJECTED", "NEW"])
    with col_f2:
        min_score = st.slider("Score ATS minimum :", 0, 100, 0)
    with col_f3:
        search_query = st.text_input("Recherche (Entreprise / Poste) :", "")
    with col_f4:
        sort_choice = st.selectbox("Trier par :", ["Score ATS ↓", "Score ATS ↑", "Plus récent", "Entreprise (A-Z)"])

    filtered_df = df.copy()
    if status_filter != "TOUS":
        filtered_df = filtered_df[filtered_df['status'] == status_filter]
    filtered_df = filtered_df[filtered_df['ats_score'] >= min_score]
    if search_query:
        query_lower = search_query.lower()
        filtered_df = filtered_df[
            filtered_df['company'].astype(str).str.lower().str.contains(query_lower, na=False) |
            filtered_df['title'].astype(str).str.lower().str.contains(query_lower, na=False)
        ]

    if sort_choice == "Score ATS ↓":
        filtered_df = filtered_df.sort_values('ats_score', ascending=False)
    elif sort_choice == "Score ATS ↑":
        filtered_df = filtered_df.sort_values('ats_score', ascending=True)
    elif sort_choice == "Plus récent":
        filtered_df = filtered_df.sort_values('created_at', ascending=False, na_position='last')
    elif sort_choice == "Entreprise (A-Z)":
        filtered_df = filtered_df.sort_values('company', ascending=True)

    st.markdown(f"**{len(filtered_df)} offre(s) correspondante(s)** sur {len(df)} au total")
    st.divider()

    if filtered_df.empty:
        st.info("Aucune offre ne correspond à ces critères.")
    else:
        for _, row in filtered_df.iterrows():
            status = row['status']
            company = row['company']
            title = row['title']
            score = row['ats_score']
            job_id = row['id']

            icon = "🟢" if status == "APPLIED" else ("🟠" if status == "PENDING_APPROVAL" else ("🔵" if status == "CV_READY" else ("🔴" if status == "REJECTED" else "⚪")))

            with st.expander(f"{icon} [{company}] {title} — Score ATS : {int(score)}% (Statut : {status})"):
                col_i1, col_i2 = st.columns(2)
                with col_i1:
                    st.write(f"**Contrat :** {row['contract_type']}")
                    st.write(f"**Plateforme :** {str(row['platform']).capitalize()}")
                    st.write(f"**Localisation :** {row['location']}")
                    st.markdown(f"**Statut :** {status_badge(status)}", unsafe_allow_html=True)
                    st.write(f"**Lien de l'offre :** [Accéder à l'annonce]({row['description_url']})")
                with col_i2:
                    st.write(f"**Compétences manquantes :** {', '.join(row['missing_skills']) if row['missing_skills'] else 'Aucune'}")
                    st.write(f"**CV sur-mesure :** `{row['tailored_cv_path']}`" if row['tailored_cv_path'] else "**CV :** Non généré")
                    st.progress(min(int(score), 100), text=f"Compatibilité ATS : {int(score)}%")

                if row['raw_description']:
                    st.text_area("Description brute", value=row['raw_description'], height=120, disabled=True, key=f"desc_box_{job_id}")

                st.markdown("### ⚡ Actions Manuelles")
                col_b1, col_b2, col_b3 = st.columns(3)

                with col_b1:
                    if st.button("✅ Valider & Marquer 'APPLIED'", key=f"btn_app_{job_id}", use_container_width=True):
                        db_up = SessionLocal()
                        try:
                            j_target = db_up.query(JobModel).filter(JobModel.id == job_id).first()
                            if j_target:
                                j_target.status = "APPLIED"
                                db_up.commit()
                                st.success(f"Candidature validée pour {company} !")
                                st.rerun()
                        finally:
                            db_up.close()

                with col_b2:
                    if st.button("❌ Rejeter l'offre", key=f"btn_rej_{job_id}", use_container_width=True):
                        db_up = SessionLocal()
                        try:
                            j_target = db_up.query(JobModel).filter(JobModel.id == job_id).first()
                            if j_target:
                                j_target.status = "REJECTED"
                                db_up.commit()
                                st.warning("Offre écartée.")
                                st.rerun()
                        finally:
                            db_up.close()

                with col_b3:
                    if st.button("🔄 Remettre en attente", key=f"btn_pend_{job_id}", use_container_width=True):
                        db_up = SessionLocal()
                        try:
                            j_target = db_up.query(JobModel).filter(JobModel.id == job_id).first()
                            if j_target:
                                j_target.status = "NEW"
                                db_up.commit()
                                st.info("Statut basculé en attente.")
                                st.rerun()
                        finally:
                            db_up.close()

# ==========================================
# TAB 4 : SUIVI DES CVS, VISUALISEUR & AUDITS
# ==========================================
elif selected_tab == "📄 Traçabilité CVs":
    st.markdown("""
        <div class="hero-banner">
            <p class="hero-title">📄 Traçabilité, Téléchargement & Visualiseur de CV</p>
            <p class="hero-subtitle">Inspecte l'historique d'exécution, prévisualise et télécharge tes CVs sur-mesure.</p>
        </div>
    """, unsafe_allow_html=True)

    if df.empty:
        st.info("Aucun historique disponible.")
    else:
        selected_job_company = st.selectbox(
            "Sélectionner une offre pour inspecter le CV et l'audit :",
            options=df['id'].tolist(),
            format_func=lambda x: f"[{df[df['id'] == x]['company'].values[0]}] {df[df['id'] == x]['title'].values[0]} (Score: {int(df[df['id'] == x]['ats_score'].values[0])}%)"
        )

        selected_row = df[df['id'] == selected_job_company].iloc[0]

        col_a1, col_a2 = st.columns([1, 1])
        with col_a1:
            st.markdown(f"### 🏢 {selected_row['company']}")
            st.write(f"**Poste :** {selected_row['title']}")
            st.markdown(f"**Statut actuel :** {status_badge(selected_row['status'])}", unsafe_allow_html=True)
            st.write(f"**Score ATS :** {int(selected_row['ats_score'])}%")
            st.progress(min(int(selected_row['ats_score']), 100))

            cv_path = selected_row['tailored_cv_path']
            if cv_path and isinstance(cv_path, (str, Path)) and Path(str(cv_path)).exists():
                st.success("✅ CV sur-mesure disponible.")
                with open(str(cv_path), "rb") as f:
                    st.download_button(
                        label="📥 Télécharger le CV Word (.docx)",
                        data=f,
                        file_name=Path(str(cv_path)).name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )
            else:
                st.warning("⚠️ Aucun fichier CV valide généré pour cette offre.")

        with col_a2:
            st.markdown("### 👀 Aperçu en direct du CV")
            if cv_path and isinstance(cv_path, (str, Path)) and Path(str(cv_path)).exists():
                cv_content = get_docx_preview(str(cv_path))
                st.markdown(
                    f"""
                    <div style="background-color: var(--secondary-background-color); padding: 16px; border-radius: 8px; height: 320px; overflow-y: scroll; border: 1px solid rgba(128,128,128,0.2); font-size: 13px;">
                        {cv_content.replace(chr(10), '<br>')}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            else:
                st.info("Aperçu indisponible (CV non généré).")

        st.divider()
        st.markdown("### 🔍 Journal d'Audit Détaillé")
        audit_logs = selected_row['audit_trail']
        if audit_logs:
            for log in audit_logs:
                st.code(log, language="text")
        else:
            st.info("Aucun log d'audit enregistré pour cette offre.")

# ==========================================
# TAB 5 : CHAT AVEC L'AGENT (EXTERNE)
# ==========================================
elif selected_tab == "💬 Chat avec l'Agent":
    st.markdown("""
        <div class="hero-banner">
            <p class="hero-title">💬 Dialogue Interactif avec l'Agent</p>
        </div>
    """, unsafe_allow_html=True)

    render_chat_tab()

# ==========================================
# TAB 6 : EXPLORATION BASE DE DONNÉES
# ==========================================
elif selected_tab == "🗄️ Base de Données":
    st.markdown("""
        <div class="hero-banner">
            <p class="hero-title">🗄️ Explorateur de Base de Données</p>
            <p class="hero-subtitle">Inspection directe des tables relationnelles PostgreSQL (`jobs` et `applications`).</p>
        </div>
    """, unsafe_allow_html=True)

    table_choice = st.radio("Sélectionner la table à inspecter :", ["jobs", "applications"], horizontal=True)

    try:
        db_exp: Session = SessionLocal()
        records = db_exp.query(JobModel).all() if table_choice == "jobs" else db_exp.query(ApplicationModel).all()
        db_exp.close()
    except Exception as e:
        st.error(f"Erreur de lecture : {e}")
        records = []

    if not records:
        st.warning(f"La table `{table_choice}` est vide.")
    else:
        raw_list = []
        for r in records:
            row_dict = {c: getattr(r, c) for c in inspect(r.__class__).columns.keys()}
            raw_list.append(row_dict)

        df_table = pd.DataFrame(raw_list)
        st.markdown(kpi_card("Nombre total d'enregistrements", len(df_table)), unsafe_allow_html=True)
        st.dataframe(df_table, use_container_width=True)

        csv_bytes = df_table.to_csv(index=False).encode('utf-8')
        st.download_button(
            label=f"📥 Exporter la table `{table_choice}` au format CSV",
            data=csv_bytes,
            file_name=f"{table_choice}_export.csv",
            mime="text/csv"
        )