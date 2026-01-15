# LaTeX to Accessible HTML Converter

A web application that converts LaTeX documents to accessible HTML using Quarto with proper semantic structure and screen reader compatibility.

## Features

- Upload ZIP files containing LaTeX documents
- Converts .tex files to accessible HTML5
- Adds semantic structure and ARIA labels
- MathJax integration for mathematical expressions
- Responsive design with accessibility considerations
- High contrast colors and readable fonts

## Requirements

- Python 3.7+
- Quarto (for LaTeX conversion)
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
   python app.py
   ```

2. Open http://localhost:5000 in your browser

3. Upload a ZIP file containing your LaTeX documents

4. Download the converted accessible HTML files

## Accessibility Features

- Semantic HTML5 structure
- Proper heading hierarchy
- Screen reader compatible math expressions
- Keyboard navigation support
- High contrast design
- Mobile responsive layout
- ARIA labels and roles