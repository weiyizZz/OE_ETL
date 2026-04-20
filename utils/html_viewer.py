import webbrowser
import tempfile

def show(text: str, title: str = "Combined Text"):
    """Render text in a temp HTML file and open it in the default browser."""
    # Preserve newlines and table separators in HTML
    html_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    html_text = html_text.replace('\n', '<br>')
    html_text = html_text.replace('---', '<hr>')

    html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <title>{title}</title>
        <style>
            body {{
                font-family: monospace;
                padding: 2rem;
                max-width: 900px;
                margin: auto;
                line-height: 1.6;
            }}
            h2 {{
                color: #333;
            }}
            hr {{
                border: none;
                border-top: 1px solid #ccc;
                margin: 1.5rem 0;
            }}
        </style>
    </head>
    <body>
        <h2>{title}</h2>
        <div>{html_text}</div>
    </body>
    </html>
    """

    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
        f.write(html)
        webbrowser.open(f'file://{f.name}')