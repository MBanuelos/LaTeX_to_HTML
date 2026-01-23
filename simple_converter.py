#!/usr/bin/env python3
"""
Simple LaTeX to HTML converter with enhanced theorem support and error handling
"""

import re
import os
import subprocess
import tempfile
import shutil

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

    def convert_framebox_parbox(text):
        pattern = re.compile(
            r'\\framebox\{\\parbox\{[^}]*\}\{([\s\S]*?)\}\}',
            re.MULTILINE
        )
        return pattern.sub(r'\\begin{quote}\n\1\n\\end{quote}', text)

    def split_comment(line):
        match = re.search(r'(?<!\\)%', line)
        if match:
            return line[:match.start()], line[match.start():]
        return line, ''

    content = convert_framebox_parbox(content)

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
        code = re.sub(r'\\begin\{multicols\}\{[^}]+\}', '', code)
        code = re.sub(r'\\end\{multicols\}', '', code)
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

def preprocess_tikz(content, work_dir):
    """Render TikZ pictures to PNG and replace them with includegraphics."""
    if shutil.which('pdflatex') is None or shutil.which('pdftoppm') is None:
        raise Exception("TikZ detected but pdflatex or pdftoppm is not installed. Install TeX Live and Poppler (pdftoppm).")

    if r'\usepackage{graphicx}' not in content:
        if r'\documentclass' in content:
            content = re.sub(
                r'(\\documentclass[^\n]*\n)',
                r'\1\\usepackage{graphicx}\n',
                content,
                count=1
            )
        else:
            content = '\\usepackage{graphicx}\n' + content

    tikz_pattern = re.compile(
        r'\\begin\{tikzpicture\}[\s\S]*?\\end\{tikzpicture\}',
        re.MULTILINE
    )
    matches = list(tikz_pattern.finditer(content))
    if not matches:
        return content, []
    png_paths = []
    new_parts = []
    last_idx = 0

    with tempfile.TemporaryDirectory(dir=work_dir) as temp_dir:
        for idx, match in enumerate(matches, start=1):
            tikz_block = match.group(0)
            tex_name = f"tikz_{idx}.tex"
            pdf_name = f"tikz_{idx}.pdf"
            png_base = f"tikz_{idx}"
            png_name = f"{png_base}.png"
            tex_path = os.path.join(temp_dir, tex_name)

            tex_content = (
                "\\documentclass[tikz]{standalone}\n"
                "\\usepackage{tikz}\n"
                "\\begin{document}\n"
                f"{tikz_block}\n"
                "\\end{document}\n"
            )
            with open(tex_path, 'w', encoding='utf-8') as f:
                f.write(tex_content)

            pdflatex_cmd = [
                'pdflatex',
                '-interaction=nonstopmode',
                '-halt-on-error',
                '-output-directory', temp_dir,
                tex_path
            ]
            result = subprocess.run(pdflatex_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Warning: TikZ render failed for block {idx}: {result.stderr}")
                continue

            pdf_path = os.path.join(temp_dir, pdf_name)
            ppm_cmd = [
                'pdftoppm',
                '-png',
                '-singlefile',
                pdf_path,
                os.path.join(temp_dir, png_base)
            ]
            result = subprocess.run(ppm_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Warning: pdftoppm failed for block {idx}: {result.stderr}")
                continue

            png_path = os.path.join(temp_dir, png_name)
            final_png = os.path.join(work_dir, png_name)
            shutil.copy2(png_path, final_png)
            png_paths.append(final_png)

            new_parts.append(content[last_idx:match.start()])
            new_parts.append(f"\\begin{{center}}\\includegraphics{{{png_name}}}\\end{{center}}")
            last_idx = match.end()

        new_parts.append(content[last_idx:])

    return ''.join(new_parts), png_paths

def preprocess_beamer_frames(content):
    """Convert beamer frames to section headings for reveal.js output"""
    def split_comment(line):
        match = re.search(r'(?<!\\)%', line)
        if match:
            return line[:match.start()], line[match.start():]
        return line, ''

    inside_frame = False
    frame_title_set = False
    output_lines = []

    for line in content.split('\n'):
        code, comment = split_comment(line)

        begin_match = re.search(r'\\begin\{frame\}(?:\[[^\]]*\])?(?:\{([^}]*)\})?', code)
        if begin_match:
            inside_frame = True
            frame_title_set = False
            title = begin_match.group(1) or ''
            if title.strip():
                output_lines.append(f'\\section{{{title.strip()}}}')
                frame_title_set = True
            code = re.sub(r'\\begin\{frame\}(?:\[[^\]]*\])?(?:\{[^}]*\})?', '', code)

        if inside_frame:
            title_match = re.search(r'\\frametitle\{([^}]*)\}', code)
            if title_match:
                title = title_match.group(1).strip()
                if title and not frame_title_set:
                    output_lines.append(f'\\section{{{title}}}')
                    frame_title_set = True
                code = re.sub(r'\\frametitle\{[^}]*\}', '', code)

        if r'\end{frame}' in code:
            code = code.replace(r'\end{frame}', '')
            inside_frame = False
            frame_title_set = False

        output_lines.append((code + comment).strip())

    return '\n'.join([line for line in output_lines if line])

def convert_latex_simple(input_file, output_file):
    """Convert LaTeX to HTML with preprocessing"""
    
    try:
        # Read input file
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Preprocess
        is_beamer = bool(re.search(r'\\documentclass(?:\[[^\]]*\])?\{beamer\}', content))
        if is_beamer:
            processed_content = preprocess_beamer_frames(content)
        else:
            processed_content = content
        processed_content, tikz_imgs = preprocess_tikz(processed_content, os.path.dirname(output_file) or '.')
        processed_content = preprocess_latex_simple(processed_content)
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tex', delete=False) as temp_file:
            temp_file.write(processed_content)
            temp_path = temp_file.name
        
        try:
            # Convert with pandoc
            cmd = [
                'pandoc', temp_path,
                '--from=latex',
                '--to=' + ('revealjs' if is_beamer else 'html5'),
                '--standalone',
                '--mathjax',
                '--resource-path=' + (os.path.dirname(output_file) or '.'),
                '--output=' + output_file
            ]
            if is_beamer:
                cmd.extend(['--variable', 'revealjs-url=https://unpkg.com/reveal.js@5'])
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"Pandoc failed: {result.stderr}")
            
            # Post-process HTML for better theorem styling
            if not is_beamer:
                post_process_html(output_file)
            for img_path in tikz_imgs:
                img_name = os.path.basename(img_path)
                dst = os.path.join(os.path.dirname(output_file), img_name)
                if dst and os.path.abspath(img_path) != os.path.abspath(dst):
                    shutil.copy2(img_path, dst)
            
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

/* Framebox-like quotes */
blockquote:not(.theorem-block) {
    margin: 1.2em 0;
    padding: 1em;
    border: 1px solid #ddd;
    background-color: #f8f9fa;
    border-radius: 4px;
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
