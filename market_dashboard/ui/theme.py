"""Shared visual theme helpers for Streamlit and Plotly."""

from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go
import plotly.io as pio


THEMES = {
    "dark": {
        "background": "#111315",
        "surface": "#191c20",
        "surface_alt": "#20242a",
        "border": "#2d333b",
        "text": "#eef2f6",
        "muted": "#a5adba",
        "primary": "#4da3ff",
        "success": "#35c46f",
        "danger": "#f05252",
        "warning": "#eab308",
        "grid": "#30363d",
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
    colors = theme_tokens(mode)
    pio.templates.default = get_plotly_template(mode)

    st.markdown(
        f"""
        <style>
        :root {{
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
        }}

        .stApp {{
            background: var(--qma-bg);
            color: var(--qma-text);
        }}

        section[data-testid="stSidebar"] {{
            background: var(--qma-surface);
            border-right: 1px solid var(--qma-border);
        }}

        h1, h2, h3 {{
            letter-spacing: 0;
            color: var(--qma-text);
        }}

        div[data-testid="stMetric"],
        div[data-testid="stExpander"] details {{
            background: var(--qma-surface);
            border: 1px solid var(--qma-border);
            border-radius: 8px;
            padding: 0.6rem 0.75rem;
        }}

        div[data-testid="stMetricLabel"] p,
        .qma-muted {{
            color: var(--qma-muted);
        }}

        .qma-panel {{
            background: var(--qma-surface);
            border: 1px solid var(--qma-border);
            border-radius: 8px;
            padding: 1rem;
        }}

        .qma-status {{
            display: inline-flex;
            align-items: center;
            border: 1px solid var(--qma-border);
            border-radius: 999px;
            color: var(--qma-muted);
            font-size: 0.82rem;
            padding: 0.16rem 0.55rem;
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
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 0.5rem;
            margin: 0.55rem 0 0.85rem;
        }}

        .qma-status-item,
        .qma-preview-item {{
            background: var(--qma-surface);
            border: 1px solid var(--qma-border);
            border-radius: 8px;
            padding: 0.45rem 0.55rem;
            min-width: 0;
        }}

        .qma-status-label,
        .qma-preview-label {{
            color: var(--qma-muted);
            font-size: 0.72rem;
            line-height: 1.1;
        }}

        .qma-status-value,
        .qma-preview-value {{
            color: var(--qma-text);
            font-size: 0.95rem;
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
            border-radius: 6px;
            border: 1px solid var(--qma-border);
            font-weight: 600;
        }}

        .stButton button[kind="primary"] {{
            background: var(--qma-primary);
            border-color: var(--qma-primary);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
