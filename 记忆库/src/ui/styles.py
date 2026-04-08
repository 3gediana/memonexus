"""UI Style Constants - Warm and cozy theme like Notion"""

# Background colors
BG_PRIMARY = "#faf9f7"
BG_SECONDARY = "#ffffff"
BG_CARD = "#ffffff"
BG_HOVER = "#f5f4f2"

# Main accent colors
COLOR_TERRACOTTA = "#e07a5f"  # Primary accent
COLOR_MINT = "#81b29a"  # Secondary accent
COLOR_GOLD = "#ffd166"  # Highlight color

# Text colors
TEXT_PRIMARY = "#2d3436"
TEXT_SECONDARY = "#636e72"
TEXT_MUTED = "#b2bec3"

# Border & Shadow
BORDER_COLOR = "#e8e8e8"
SHADOW = "0 2px 8px rgba(0,0,0,0.08)"

# Border radius
RADIUS_SM = "8px"
RADIUS_MD = "12px"
RADIUS_LG = "16px"

# Key colors for memory network (up to 10 distinct colors)
KEY_COLORS = [
    "#e07a5f",  # Terracotta
    "#81b29a",  # Mint
    "#3d5a80",  # Navy
    "#ee6c4d",  # Coral
    "#98c1d9",  # Sky blue
    "#a7c957",  # Lime
    "#f4a261",  # Sand
    "#9b5de5",  # Purple
    "#00f5d4",  # Cyan
    "#ffd166",  # Gold
]

# Status colors
STATUS_SUCCESS = "#81b29a"
STATUS_WARNING = "#f4a261"
STATUS_ERROR = "#e07a5f"
STATUS_INFO = "#3d5a80"

# CSS for custom styling
CUSTOM_CSS = """
:root {
    --bg-primary: #faf9f7;
    --bg-secondary: #ffffff;
    --color-terracotta: #e07a5f;
    --color-mint: #81b29a;
    --color-gold: #ffd166;
    --text-primary: #2d3436;
    --text-secondary: #636e72;
    --border-color: #e8e8e8;
    --radius: 12px;
}

body, body {{ background: var(--bg-primary) !important; }}

.gradio-container {{ background: var(--bg-primary) !important; }}

.card {{
    background: var(--bg-secondary);
    border-radius: var(--radius);
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    padding: 16px;
    margin: 8px 0;
}}

.tab-content {{
    background: var(--bg-secondary);
    border-radius: var(--radius);
    padding: 16px;
}}

/* Memory highlight */
.memory-highlight {{
    background: linear-gradient(120deg, #ffd166 0%, #ffd166 100%);
    background-repeat: no-repeat;
    background-size: 100% 40%;
    background-position: 0 90%;
}}

/* Event log */
.event-log {{
    font-family: 'Monaco', 'Menlo', monospace;
    font-size: 12px;
}}

.event-item {{ padding: 4px 8px; border-radius: 4px; margin: 2px 0; }}
.event-reasoning {{ background: #f0f0f0; }}
.event-tool {{ background: #e8f4f0; }}
.event-reply {{ background: #fff4e0; }}

/* SUB record */
.sub-record {{ padding: 8px; border-bottom: 1px solid var(--border-color); }}
.sub-time {{ color: var(--text-secondary); font-size: 11px; }}
.sub-message {{ margin-top: 4px; }}
"""
