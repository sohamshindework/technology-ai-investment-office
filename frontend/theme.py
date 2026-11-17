"""Editorial theme tokens shared by CSS and Plotly."""

TOKENS = {
    "canvas": "#F7F8F5",
    "surface": "#FFFFFF",
    "subtle": "#F0F3F1",
    "primary": "#24332F",
    "body": "#40524C",
    "muted": "#718078",
    "border": "#E0E6E1",
    "accent": "#276E65",
    "hover": "#1D5952",
    "light-accent": "#E2EEEA",
    "positive": "#368169",
    "warning": "#B08043",
    "negative": "#B65F5D",
}
CHART_COLORS = [TOKENS["accent"], "#76A99E", "#496E83", TOKENS["warning"], TOKENS["negative"], "#718078"]


def css_variables(accent=None):
    values = {**TOKENS, "accent": accent or TOKENS["accent"]}
    if accent and accent != TOKENS["accent"]:
        values["hover"] = f"color-mix(in srgb, {accent} 82%, black)"
        values["light-accent"] = f"color-mix(in srgb, {accent} 12%, white)"
    return ":root {" + "".join(f"--{key}:{value};" for key, value in values.items()) + "}"
