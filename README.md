# LaTeX to Accessible HTML Converter

A web application that converts LaTeX documents to accessible HTML using Quarto (with a Pandoc fallback) and adds accessibility-focused structure and styling.

## Features

- Upload ZIP files containing LaTeX documents
- Converts .tex files to accessible HTML5
- Preserves a named HTML file (same base name as the input) for Quarto outputs
- Falls back to single-file Pandoc conversion if Quarto render fails
- Adds semantic structure and ARIA labels
- MathJax integration for mathematical expressions
- Responsive design with accessibility considerations
- High contrast colors and readable fonts

## Requirements

- Python 3.7+
- Quarto (for multi-page site conversion)
- Flask

## Installation

1. Install Quarto:
   ```bash
   # Visit https://quarto.org/docs/get-started/
   # Or use homebrew on macOS:
   brew install quarto
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Start the application:
   ```bash
   ./run.sh
   ```

2. Open http://localhost:8000 in your browser

3. Upload a ZIP file containing your LaTeX documents

4. Download the converted accessible HTML files

### Windows

1. Start the application:
   ```bat
   run.bat
   ```

2. Open http://localhost:8000 in your browser

## Configuration

- `FLASK_SECRET_KEY`: set a secret key for sessions (recommended).
- `FLASK_DEBUG`: set to `1` to enable debug mode.
- `PORT`: change the port (default `8000`).

## Output Notes

- Single-file conversions output `output/<name>/<name>.html`.
- Quarto conversions keep `index.html` for the site and also copy it to `<name>.html` in the same folder.

## Accessibility Features

- Semantic HTML5 structure
- Proper heading hierarchy
- Screen reader compatible math expressions
- Keyboard navigation support
- High contrast design
- Mobile responsive layout
- ARIA labels and roles
