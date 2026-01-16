#!/usr/bin/env python3
"""
Simple LaTeX to HTML converter with enhanced theorem support and error handling
"""

import re
import os
import subprocess
import tempfile

def preprocess_latex_simple(content):
    """Simple but effective LaTeX preprocessing"""

    # Theorem environment mappings
    theorem_envs = {
        'definition': 'Definition',
        'theorem': 'Theorem',
        'lemma': 'Lemma',
        'corollary': 'Corollary',
        'proposition': 'Proposition',
        'remark': 'Remark',
        'example': 'Example',
        'exercise': 'Exercise',
        'proof': 'Proof'
    }

    def extract_title_info(text):
        title_match = re.search(r'\\title\{([^}]*)\}', text)
        author_match = re.search(r'\\author\{([^}]*)\}', text)
        date_match = re.search(r'\\date\{([^}]*)\}', text)

        title = title_match.group(1).strip() if title_match else ''
        author = author_match.group(1).strip() if author_match else ''
        date = date_match.group(1).strip() if date_match else ''
        return title, author, date

    def build_title_block(title, author, date):
        if not title and not author and not date:
            return None

        lines = [r'\begin{center}']
        if title:
            lines.append(r'{\LARGE ' + title + r'\par}')
        if author:
            lines.append(r'\vspace{0.5em}')
            lines.append(r'{\large ' + author + r'\par}')
        if date:
            lines.append(r'\vspace{0.5em}')
            lines.append(r'{\large ' + date + r'\par}')
        lines.append(r'\end{center}')
        return '\n'.join(lines)

    def split_comment(line):
        match = re.search(r'(?<!\\)%', line)
        if match:
            return line[:match.start()], line[match.start():]
        return line, ''

    title, author, date = extract_title_info(content)
    title_block = build_title_block(title, author, date)
    if title_block:
        if r'\maketitle' in content:
            content = content.replace(r'\maketitle', title_block)
        elif r'\begin{document}' in content:
            content = content.replace(r'\begin{document}', r'\begin{document}' + '\n' + title_block, 1)
        else:
            content = title_block + '\n' + content

    # Process theorem environments with blockquote wrappers, skipping comments
    lines = content.split('\n')
    updated_lines = []
    for line in lines:
        code, comment = split_comment(line)
        for env_name, display_name in theorem_envs.items():
            begin_pattern = rf'\\begin\{{{env_name}\}}(?:\[(?P<title>[^\]]+)\])?'
            end_pattern = rf'\\end\{{{env_name}\}}'

            def replace_begin(match):
                title = match.group('title')
                title_suffix = f" ({title})" if title else ""
                return f'\\begin{{quote}}\n\\textbf{{{display_name}{title_suffix}:}} '

            code = re.sub(begin_pattern, replace_begin, code)
            code = re.sub(end_pattern, r'\\end{quote}', code)
        updated_lines.append(code + comment)
    content = '\n'.join(updated_lines)

    # Handle labels and references better
    content = re.sub(r'\\label\{([^}]+)\}', r'', content)  # Remove labels for now
    content = re.sub(r'\\ref\{([^}]+)\}', r'\\textit{\\1}', content)  # Convert refs to italic

    return content

def convert_latex_simple(input_file, output_file):
    """Convert LaTeX to HTML with preprocessing"""
    
    try:
        # Read input file
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Preprocess
        processed_content = preprocess_latex_simple(content)
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tex', delete=False) as temp_file:
            temp_file.write(processed_content)
            temp_path = temp_file.name
        
        try:
            # Convert with pandoc
            cmd = [
                'pandoc', temp_path,
                '--from=latex',
                '--to=html5',
                '--standalone',
                '--mathjax',
                '--output=' + output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"Pandoc failed: {result.stderr}")
            
            # Post-process HTML for better theorem styling
            post_process_html(output_file)
            
            return True
            
        finally:
            # Clean up temp file
            os.unlink(temp_path)
            
    except Exception as e:
        raise Exception(f"Conversion failed: {str(e)}")

def post_process_html(html_file):
    """Add enhanced styling to the HTML output"""
    
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add custom CSS for theorem-like environments
    custom_css = """
<style>
/* Enhanced theorem styling */
body { 
    font-family: 'Times New Roman', serif; 
    line-height: 1.6; 
    max-width: 1200px; 
    margin: 0 6vw 0 2vw; 
    padding: 20px; 
}

/* Theorem-like environments */
.theorem-block {
    margin: 1.5em 0;
    padding: 1em;
    border-left: 4px solid #007acc;
    background-color: #f8f9fa;
    border-radius: 4px;
}

.theorem-block > p:first-child {
    margin-top: 0;
}

.theorem-block > p:last-child {
    margin-bottom: 0;
}

/* Specific colors for different types */
.theorem-block[data-theorem="definition"] {
    border-left-color: #dc3545;
    background-color: #fff8f8;
}

.theorem-block[data-theorem="theorem"],
.theorem-block[data-theorem="lemma"],
.theorem-block[data-theorem="corollary"],
.theorem-block[data-theorem="proposition"] {
    border-left-color: #28a745;
    background-color: #f8fff8;
}

.theorem-block[data-theorem="example"],
.theorem-block[data-theorem="exercise"] {
    border-left-color: #ffc107;
    background-color: #fffdf0;
}

.theorem-block[data-theorem="proof"] {
    border-left-color: #6c757d;
    background-color: #f1f3f4;
}

/* Math styling */
.math { font-family: 'Times New Roman', serif; }

/* Accessibility */
@media (prefers-reduced-motion: reduce) { 
    * { animation-duration: 0.01ms !important; } 
}
</style>
"""
    
    # Add theorem classes to blockquotes
    theorem_keywords = ['Definition:', 'Theorem:', 'Lemma:', 'Corollary:', 'Proposition:', 'Remark:', 'Example:', 'Exercise:', 'Proof:']
    for keyword in theorem_keywords:
        env_name = keyword.lower().replace(':', '')
        pattern = re.compile(rf'<blockquote>(\s*<p>\s*<strong>{re.escape(keyword)}</strong>)')
        content = pattern.sub(
            rf'<blockquote class="theorem-block" data-theorem="{env_name}">\1',
            content
        )

    # Insert CSS before closing head tag
    if '</head>' in content:
        content = content.replace('</head>', custom_css + '</head>')
    
    # Add lang attribute if missing
    content = re.sub(r'<html(?![^>]*\blang=)([^>]*)>', r'<html\1 lang="en">', content, count=1)
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python simple_converter.py input.tex output.html")
        sys.exit(1)
    
    try:
        convert_latex_simple(sys.argv[1], sys.argv[2])
        print(f"Successfully converted {sys.argv[1]} to {sys.argv[2]}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
