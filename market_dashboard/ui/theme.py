"""Shared visual theme helpers for Streamlit and Plotly."""

from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go
import plotly.io as pio


THEMES = {
    "dark": {
        "background": "#07090d",
        "surface": "#0d1118",
        "surface_alt": "#131a23",
        "border": "#26313d",
        "text": "#e5edf5",
        "muted": "#8a9aab",
        "primary": "#3b82f6",
        "success": "#13b66b",
        "danger": "#ef4444",
        "warning": "#f5c84c",
        "grid": "#202a35",
    },
    "light": {
        "background": "#f7f8fa",
        "surface": "#ffffff",
        "surface_alt": "#f1f4f8",
        "border": "#d9dee7",
        "text": "#1b2530",
        "muted": "#596577",
        "primary": "#1769e0",
        "success": "#168a48",
        "danger": "#c92a2a",
        "warning": "#b7791f",
        "grid": "#e2e8f0",
    },
}


def theme_tokens(mode: str | None = None) -> dict[str, str]:
    """Return the design tokens for the requested theme."""
    normalized = (mode or "dark").lower()
    return THEMES.get(normalized, THEMES["dark"])


def _register_plotly_templates() -> None:
    """Register app-specific Plotly templates once."""
    for mode, colors in THEMES.items():
        template_name = f"qma_{mode}"
        if template_name in pio.templates:
            continue

        pio.templates[template_name] = go.layout.Template(
            layout={
                "paper_bgcolor": colors["background"],
                "plot_bgcolor": colors["surface"],
                "font": {"color": colors["text"], "family": "Inter, Segoe UI, Arial, sans-serif"},
                "colorway": [
                    colors["primary"],
                    colors["success"],
                    colors["danger"],
                    colors["warning"],
                    "#8b5cf6",
                    "#14b8a6",
                ],
                "xaxis": {
                    "gridcolor": colors["grid"],
                    "linecolor": colors["border"],
                    "zerolinecolor": colors["border"],
                },
                "yaxis": {
                    "gridcolor": colors["grid"],
                    "linecolor": colors["border"],
                    "zerolinecolor": colors["border"],
                },
                "legend": {"orientation": "h", "y": 1.02, "x": 0},
                "margin": {"l": 40, "r": 24, "t": 64, "b": 40},
            }
        )


def get_plotly_template(mode: str | None = None) -> str:
    """Return the app Plotly template name for the requested mode."""
    _register_plotly_templates()
    normalized = (mode or "dark").lower()
    return "qma_light" if normalized == "light" else "qma_dark"


def apply_app_theme(mode: str | None = None) -> None:
    """Apply the shared CSS and Plotly theme."""
    normalized = (mode or "dark").lower()
    colors = theme_tokens(mode)
    pio.templates.default = get_plotly_template(mode)
    color_scheme = "light" if normalized == "light" else "dark"
    shadow = "0 1px 2px rgba(15, 23, 42, 0.06)" if color_scheme == "light" else "none"

    st.markdown(
        f"""
        <style>
        :root {{
            color-scheme: {color_scheme};
            --primary-color: {colors["primary"]};
            --background-color: {colors["background"]};
            --secondary-background-color: {colors["surface"]};
            --text-color: {colors["text"]};
            --border-color: {colors["border"]};
            --qma-bg: {colors["background"]};
            --qma-surface: {colors["surface"]};
            --qma-surface-alt: {colors["surface_alt"]};
            --qma-border: {colors["border"]};
            --qma-text: {colors["text"]};
            --qma-muted: {colors["muted"]};
            --qma-primary: {colors["primary"]};
            --qma-success: {colors["success"]};
            --qma-danger: {colors["danger"]};
            --qma-warning: {colors["warning"]};
            --qma-shadow: {shadow};
        }}

        html,
        body,
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"],
        [data-testid="stVerticalBlock"],
        .main {{
            background: var(--qma-bg);
            color: var(--qma-text);
        }}

        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"] {{
            background: transparent;
        }}

        [data-testid="stMainBlockContainer"] {{
            max-width: none;
            padding-top: 0.65rem;
            padding-left: 1.05rem;
            padding-right: 1.05rem;
        }}

        hr {{
            border-color: var(--qma-border);
            margin: 0.85rem 0;
        }}

        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div {{
            background: var(--qma-surface);
            color: var(--qma-text);
            border-right: 1px solid var(--qma-border);
        }}

        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
            gap: 0.45rem;
        }}

        h1, h2, h3, h4, h5, h6,
        p, li, label, span,
        div[data-testid="stMarkdownContainer"],
        div[data-testid="stMarkdownContainer"] * {{
            letter-spacing: 0;
            color: var(--qma-text);
        }}

        h1 {{
            font-size: 1.45rem;
            line-height: 1.15;
            margin-bottom: 0.35rem;
        }}

        h2, h3 {{
            font-size: 1.05rem;
            line-height: 1.2;
            margin-top: 0.55rem;
            margin-bottom: 0.4rem;
        }}

        small,
        div[data-testid="stCaptionContainer"],
        div[data-testid="stCaptionContainer"] *,
        div[data-testid="stWidgetLabel"] p,
        div[data-testid="stMetricLabel"] p,
        .qma-muted {{
            color: var(--qma-muted);
        }}

        div[data-testid="stMetric"],
        div[data-testid="stExpander"] details {{
            background: var(--qma-surface);
            border: 1px solid var(--qma-border);
            border-radius: 6px;
            padding: 0.5rem 0.6rem;
            box-shadow: var(--qma-shadow);
        }}

        div[data-testid="stExpander"] summary,
        div[data-testid="stExpander"] summary * {{
            color: var(--qma-text);
        }}

        [data-testid="stAlert"] {{
            background: var(--qma-surface-alt);
            color: var(--qma-text);
            border: 1px solid var(--qma-border);
            border-radius: 8px;
        }}

        [data-testid="stAlert"] *,
        [data-testid="stNotification"] * {{
            color: var(--qma-text);
        }}

        div[data-testid="stDataFrame"],
        div[data-testid="stTable"] {{
            background: var(--qma-surface);
            border: 1px solid var(--qma-border);
            border-radius: 6px;
            box-shadow: var(--qma-shadow);
        }}

        div[data-testid="stDataFrame"] * {{
            font-size: 0.78rem;
        }}

        div[data-baseweb="input"] > div,
        div[data-baseweb="base-input"],
        div[data-baseweb="select"] > div,
        div[data-baseweb="textarea"] textarea,
        input,
        textarea {{
            background: var(--qma-surface-alt);
            color: var(--qma-text);
            border-color: var(--qma-border);
        }}

        div[data-baseweb="input"] input,
        div[data-baseweb="base-input"] input,
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] input,
        div[data-baseweb="textarea"] textarea,
        input::placeholder,
        textarea::placeholder {{
            color: var(--qma-muted);
        }}

        div[data-baseweb="popover"],
        div[data-baseweb="menu"],
        ul[role="listbox"],
        li[role="option"] {{
            background: var(--qma-surface);
            color: var(--qma-text);
            border-color: var(--qma-border);
        }}

        li[role="option"]:hover,
        li[role="option"][aria-selected="true"] {{
            background: var(--qma-surface-alt);
        }}

        div[role="radiogroup"],
        div[role="radiogroup"] label,
        div[role="radiogroup"] p,
        label[data-baseweb="checkbox"],
        label[data-baseweb="radio"] {{
            color: var(--qma-text);
        }}

        button[data-baseweb="tab"],
        button[data-baseweb="tab"] p {{
            color: var(--qma-muted);
        }}

        button[data-baseweb="tab"][aria-selected="true"],
        button[data-baseweb="tab"][aria-selected="true"] p {{
            color: var(--qma-primary);
        }}

        .qma-panel {{
            background: var(--qma-surface);
            border: 1px solid var(--qma-border);
            border-radius: 6px;
            padding: 0.85rem;
            box-shadow: var(--qma-shadow);
        }}

        .qma-topbar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            background: var(--qma-surface);
            border: 1px solid var(--qma-border);
            border-top: 2px solid var(--qma-warning);
            border-radius: 6px;
            padding: 0.52rem 0.7rem;
            margin: 0.25rem 0 0.55rem;
            box-shadow: var(--qma-shadow);
        }}

        .qma-topbar-title {{
            font-size: 1.05rem;
            font-weight: 750;
            line-height: 1.1;
            color: var(--qma-text);
        }}

        .qma-topbar-subtitle {{
            color: var(--qma-muted);
            font-size: 0.78rem;
            margin-top: 0.15rem;
        }}

        .qma-topbar-meta {{
            display: flex;
            align-items: center;
            justify-content: flex-end;
            flex-wrap: wrap;
            gap: 0.4rem;
            color: var(--qma-muted);
            font-size: 0.78rem;
        }}

        .qma-quote-header {{
            display: grid;
            grid-template-columns: minmax(130px, 0.35fr) 1fr;
            gap: 0.75rem;
            align-items: stretch;
            background: var(--qma-surface);
            border: 1px solid var(--qma-border);
            border-radius: 6px;
            padding: 0.55rem;
            margin: 0.45rem 0 0.7rem;
        }}

        .qma-quote-symbol {{
            color: var(--qma-text);
            font-size: 1.25rem;
            font-weight: 800;
            line-height: 1.1;
        }}

        .qma-quote-price {{
            color: var(--qma-text);
            font-size: 1.05rem;
            font-weight: 750;
            margin-top: 0.22rem;
        }}

        .qma-quote-strip {{
            margin: 0;
        }}

        .qma-price-up {{
            color: var(--qma-success);
        }}

        .qma-price-down {{
            color: var(--qma-danger);
        }}

        .qma-status {{
            display: inline-flex;
            align-items: center;
            border: 1px solid var(--qma-border);
            border-radius: 999px;
            color: var(--qma-muted);
            font-size: 0.74rem;
            padding: 0.12rem 0.48rem;
            background: var(--qma-surface-alt);
        }}

        .qma-status-live {{
            color: var(--qma-success);
            border-color: color-mix(in srgb, var(--qma-success) 45%, var(--qma-border));
        }}

        .qma-status-demo,
        .qma-status-partial {{
            color: var(--qma-warning);
            border-color: color-mix(in srgb, var(--qma-warning) 45%, var(--qma-border));
        }}

        .qma-status-unavailable {{
            color: var(--qma-danger);
            border-color: color-mix(in srgb, var(--qma-danger) 45%, var(--qma-border));
        }}

        .qma-status-strip,
        .qma-data-summary,
        .qma-order-preview {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
            gap: 0.38rem;
            margin: 0.45rem 0 0.65rem;
        }}

        .qma-status-item,
        .qma-preview-item {{
            background: var(--qma-surface-alt);
            border: 1px solid var(--qma-border);
            border-radius: 5px;
            padding: 0.34rem 0.45rem;
            min-width: 0;
            box-shadow: var(--qma-shadow);
        }}

        .qma-status-label,
        .qma-preview-label {{
            color: var(--qma-muted);
            font-size: 0.68rem;
            line-height: 1.1;
            text-transform: uppercase;
        }}

        .qma-status-value,
        .qma-preview-value {{
            color: var(--qma-text);
            font-size: 0.9rem;
            font-weight: 650;
            margin-top: 0.1rem;
            overflow-wrap: anywhere;
        }}

        .qma-section-title {{
            color: var(--qma-text);
            font-size: 1rem;
            font-weight: 700;
            margin: 0.6rem 0 0.35rem;
        }}

        .stButton button {{
            background: var(--qma-surface);
            color: var(--qma-text);
            border-radius: 4px;
            border: 1px solid var(--qma-border);
            font-weight: 650;
            min-height: 2rem;
            padding: 0.28rem 0.55rem;
        }}

        .stButton button[kind="primary"] {{
            background: var(--qma-primary);
            border-color: var(--qma-primary);
            color: #ffffff;
        }}

        .stButton button:hover {{
            border-color: var(--qma-primary);
            color: var(--qma-primary);
        }}

        .stButton button[kind="primary"]:hover {{
            color: #ffffff;
        }}

        @media (max-width: 760px) {{
            .qma-topbar,
            .qma-quote-header {{
                grid-template-columns: 1fr;
                flex-direction: column;
                align-items: stretch;
            }}

            .qma-topbar-meta {{
                justify-content: flex-start;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
