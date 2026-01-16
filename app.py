from flask import Flask, request, render_template, send_file, flash, redirect, url_for
import os
import zipfile
import subprocess
import tempfile
import shutil
import re
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
ALLOWED_EXTENSIONS = {'zip', 'tex', 'latex'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def preprocess_latex(latex_content):
    """Simple but effective LaTeX preprocessing for theorem environments"""

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

    # Process theorem environments with blockquote wrappers
    for env_name, display_name in theorem_envs.items():
        begin_pattern = rf'\\begin\{{{env_name}\}}(?:\[(?P<title>[^\]]+)\])?'
        end_pattern = rf'\\end\{{{env_name}\}}'

        def replace_begin(match):
            title = match.group('title')
            title_suffix = f" ({title})" if title else ""
            return f'\\begin{{quote}}\n\\textbf{{{display_name}{title_suffix}:}} '

        latex_content = re.sub(begin_pattern, replace_begin, latex_content)
        latex_content = re.sub(end_pattern, '\n\\\\end{quote}\n', latex_content)

    # Handle labels and references
    latex_content = re.sub(r'\\label\{([^}]+)\}', r'', latex_content)  # Remove labels
    latex_content = re.sub(r'\\ref\{([^}]+)\}', r'\\textit{\1}', latex_content)  # Convert refs to italic

    return latex_content

def resolve_includes(latex_content, base_dir):
    """Resolve \\include and \\input commands"""
    lines = latex_content.split('\n')
    resolved_lines = []
    
    for line in lines:
        # Handle \\include{filename} and \\input{filename}
        include_match = re.search(r'\\(?:include|input)\{([^}]+)\}', line)
        if include_match:
            filename = include_match.group(1)
            if not filename.endswith('.tex'):
                filename += '.tex'
            
            include_path = os.path.join(base_dir, filename)
            # Try with .tex extension if file doesn't exist
            if not os.path.exists(include_path) and not filename.endswith('.tex'):
                include_path = os.path.join(base_dir, filename + '.tex')
            
            if os.path.exists(include_path):
                with open(include_path, 'r', encoding='utf-8', errors='ignore') as f:
                    included_content = f.read()
                # Recursively resolve includes in the included file
                included_content = resolve_includes(included_content, base_dir)
                resolved_lines.append(included_content)
            else:
                print(f"Warning: Could not find include file: {filename}")
                resolved_lines.append(line)  # Keep original if file not found
        else:
            resolved_lines.append(line)
    
    return '\n'.join(resolved_lines)

def create_quarto_website(latex_file_path, output_dir):
    """Create Quarto website with sidebar navigation based on chapters/sections"""
    work_dir = os.path.dirname(latex_file_path)
    
    # Read and resolve all includes first
    with open(latex_file_path, 'r', encoding='utf-8', errors='ignore') as f:
        latex_content = f.read()
    
    resolved_content = resolve_includes(latex_content, work_dir)
    processed_content = preprocess_latex(resolved_content)
    
    # Find chapters and sections for sidebar
    sidebar_items = []
    for line in processed_content.split('\n'):
        chapter_match = re.search(r'\\chapter\{([^}]+)\}', line)
        section_match = re.search(r'\\section\{([^}]+)\}', line)
        
        if chapter_match:
            title = chapter_match.group(1)
            # Clean title for YAML compatibility
            title = title.replace('$', '').replace('\\', '').replace('^', '').replace('_', '')
            sidebar_items.append({'text': title, 'level': 'chapter'})
        elif section_match:
            title = section_match.group(1)
            # Clean title for YAML compatibility  
            title = title.replace('$', '').replace('\\', '').replace('^', '').replace('_', '')
            sidebar_items.append({'text': title, 'level': 'section'})
    
    # Create _quarto.yml with left sidebar
    if sidebar_items:
        sidebar_content = '\n'.join([
            f'      - text: "{item["text"]}"'
            for item in sidebar_items
        ])
    else:
        sidebar_content = '      - index.qmd'
    
    quarto_config = f"""project:
  type: website

website:
  title: "LaTeX Document"
  search:
    location: sidebar
    type: textbox
  sidebar:
    style: "floating"
    search: true

format:
  html:
    theme: cosmo
    toc: true
    toc-location: right
    number-sections: true
    number-depth: 3
"""
    
    with open(os.path.join(work_dir, '_quarto.yml'), 'w') as f:
        f.write(quarto_config)
    
    # Convert LaTeX to markdown using pandoc
    temp_tex = os.path.join(work_dir, 'temp_full.tex')
    temp_md = os.path.join(work_dir, 'temp_content.md')
    
    with open(temp_tex, 'w', encoding='utf-8') as f:
        f.write(processed_content)
    
    # Use pandoc to convert LaTeX to markdown
    pandoc_cmd = [
        'pandoc', 'temp_full.tex',
        '--from=latex+raw_tex',
        '--to=markdown',
        '--output=temp_content.md'
    ]
    
    subprocess.run(pandoc_cmd, cwd=work_dir, capture_output=True, check=True)
    
    # Read converted markdown
    with open(temp_md, 'r', encoding='utf-8') as f:
        markdown_content = f.read()
    
    # Create index.qmd with converted content
    with open(os.path.join(work_dir, 'index.qmd'), 'w') as f:
        f.write(f'---\ntitle: "Document"\n---\n\n{markdown_content}')
    
    # Clean up temp files
    for temp_file in [temp_tex, temp_md]:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    # Render Quarto website
    try:
        subprocess.run(['quarto', 'render'], cwd=work_dir, capture_output=True, check=True)
        
        # Copy _site contents to output directory
        site_dir = os.path.join(work_dir, '_site')
        if os.path.exists(site_dir):
            for item in os.listdir(site_dir):
                src = os.path.join(site_dir, item)
                dst = os.path.join(output_dir, item)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
        for root, _, files in os.walk(output_dir):
            for filename in files:
                if filename.endswith('.html'):
                    enhance_html_accessibility(os.path.join(root, filename))
        return True
    except subprocess.CalledProcessError as e:
        raise Exception(f"Quarto render failed: {e.stderr}")

def convert_latex_to_html(latex_file_path, output_path):
    """Convert LaTeX to HTML with enhanced error handling and theorem support"""
    work_dir = os.path.dirname(latex_file_path)
    output_dir = os.path.dirname(output_path)
    
    try:
        # Validate input file
        if not os.path.exists(latex_file_path):
            raise FileNotFoundError(f"LaTeX file not found: {latex_file_path}")
        
        with open(latex_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if not content.strip():
            raise ValueError("LaTeX file is empty")
        
        # Check for common LaTeX errors
        validation_errors = validate_latex_content(content)
        if validation_errors:
            print(f"Warning: LaTeX validation issues found: {'; '.join(validation_errors)}")
        
        if re.search(r'\\(?:include|input|chapter|section)\{[^}]+\}', content):
            # Create Quarto website with sidebar
            return create_quarto_website(latex_file_path, output_dir)
        else:
            # Single file conversion with preprocessing
            processed_content = preprocess_latex(content)
            
            # Write preprocessed content to temp file
            temp_tex = os.path.join(work_dir, 'temp_processed.tex')
            with open(temp_tex, 'w', encoding='utf-8') as f:
                f.write(processed_content)
            
            pandoc_cmd = [
                'pandoc', temp_tex,
                '--from=latex',
                '--to=html5',
                '--standalone',
                '--mathjax',
                '--output=' + output_path
            ]
            
            result = subprocess.run(pandoc_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                error_msg = f"Pandoc conversion failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                raise Exception(error_msg)
            
            # Clean up temp file
            if os.path.exists(temp_tex):
                os.remove(temp_tex)

            enhance_html_accessibility(output_path)
            
            return True
            
    except FileNotFoundError as e:
        raise Exception(f"File error: {str(e)}")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Conversion process failed: {e.stderr.decode() if e.stderr else 'Unknown error'}")
    except Exception as e:
        raise Exception(f"Conversion error: {str(e)}")

def validate_latex_content(content):
    """Validate LaTeX content and return list of potential issues"""
    errors = []
    
    # Check for unmatched braces
    open_braces = content.count('{')
    close_braces = content.count('}')
    if open_braces != close_braces:
        errors.append(f"Unmatched braces: {open_braces} open, {close_braces} close")
    
    # Check for common undefined commands
    undefined_commands = []
    common_commands = ['textbf', 'textit', 'emph', 'section', 'subsection', 'chapter', 'title', 'author', 'date', 'today', 'maketitle', 'ref', 'label']
    for match in re.finditer(r'\\([a-zA-Z]+)', content):
        cmd = match.group(1)
        if cmd not in common_commands and len(cmd) > 2:
            if cmd not in ['begin', 'end', 'documentclass', 'usepackage']:
                undefined_commands.append(cmd)
    
    if undefined_commands:
        unique_cmds = list(set(undefined_commands))[:5]  # Limit to 5
        errors.append(f"Potentially undefined commands: {', '.join(unique_cmds)}")
    
    # Check for missing document structure
    if '\\documentclass' not in content and '\\begin{document}' not in content:
        errors.append("Missing document structure (\\documentclass or \\begin{document})")
    
    return errors

def enhance_html_accessibility(html_path):
    """Add accessibility enhancements and theorem styling to HTML"""
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Add data attributes to theorem paragraphs for better styling
        theorem_keywords = ['Definition:', 'Theorem:', 'Lemma:', 'Corollary:', 'Proposition:', 'Remark:', 'Example:', 'Exercise:', 'Proof:']
        for keyword in theorem_keywords:
            env_name = keyword.lower().replace(':', '')
            # Add data attribute to paragraphs containing theorem keywords
            pattern = f'<p><strong>{keyword}</strong>'
            replacement = f'<p data-theorem="{env_name}"><strong>{keyword}</strong>'
            content = content.replace(pattern, replacement)
            # Also handle cases where strong tags are at the beginning of paragraphs
            pattern2 = f'<strong>{keyword}</strong>'
            replacement2 = f'<strong class="theorem-label">{keyword}</strong>'
            content = content.replace(pattern2, replacement2)
            # Add theorem classes to blockquotes
            blockquote_pattern = re.compile(rf'<blockquote>(\s*<p>\s*<strong>{re.escape(keyword)}</strong>)')
            content = blockquote_pattern.sub(
                rf'<blockquote class="theorem-block" data-theorem="{env_name}">\1',
                content
            )
        
        # Enhanced accessibility CSS with theorem support
        accessibility_css = """
<style>
/* Accessibility enhancements */
body { font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }
h1, h2, h3, h4, h5, h6 { margin-top: 1.5em; margin-bottom: 0.5em; }
p { margin-bottom: 1em; }
img { max-width: 100%; height: auto; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
th { background-color: #f2f2f2; font-weight: bold; }
a { color: #0066cc; text-decoration: underline; }
a:hover, a:focus { background-color: #f0f8ff; }
.math { font-family: 'Times New Roman', serif; }
@media (prefers-reduced-motion: reduce) { * { animation-duration: 0.01ms !important; } }

/* Enhanced theorem styling */
body { font-family: 'Times New Roman', serif; }

/* Theorem labels - make them bold and colored */
.theorem-label,
strong.theorem-label {
    color: #007acc !important;
    font-size: 1.1em !important;
    font-weight: bold !important;
}

/* Style paragraphs with theorem data attributes */
p[data-theorem] {
    margin: 1.5em 0;
    padding: 1em;
    border-left: 4px solid #007acc;
    background-color: #f8f9fa;
    border-radius: 4px;
}

/* Theorem blockquotes */
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

/* Specific styling based on content */
p[data-theorem="definition"],
.theorem-block[data-theorem="definition"] {
    border-left-color: #dc3545;
    background-color: #fff8f8;
}

p[data-theorem="theorem"],
p[data-theorem="lemma"],
p[data-theorem="corollary"],
p[data-theorem="proposition"],
.theorem-block[data-theorem="theorem"],
.theorem-block[data-theorem="lemma"],
.theorem-block[data-theorem="corollary"],
.theorem-block[data-theorem="proposition"] {
    border-left-color: #28a745;
    background-color: #f8fff8;
}

p[data-theorem="example"],
p[data-theorem="exercise"],
.theorem-block[data-theorem="example"],
.theorem-block[data-theorem="exercise"] {
    border-left-color: #ffc107;
    background-color: #fffdf0;
}

p[data-theorem="proof"],
.theorem-block[data-theorem="proof"] {
    border-left-color: #6c757d;
    background-color: #f1f3f4;
}
</style>
"""
        
        # Insert CSS before closing head tag
        if '</head>' in content:
            content = content.replace('</head>', accessibility_css + '</head>')
        else:
            # If no head tag, add it
            content = '<head>' + accessibility_css + '</head>' + content
        
        # Add lang attribute if missing
        if 'lang=' not in content:
            content = content.replace('<html>', '<html lang="en">')
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
    except Exception as e:
        print(f"Warning: Could not enhance HTML accessibility: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file selected')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        try:
            if filename.lower().endswith('.zip'):
                # Process ZIP file
                output_dir = process_latex_zip(filepath)
            else:
                # Process single LaTeX file
                output_dir = process_single_latex_file(filepath)
            return render_template('success.html', output_dir=output_dir)
        except Exception as e:
            flash(f'Error processing file: {str(e)}')
            return redirect(url_for('index'))
    
    flash('Invalid file type. Please upload a ZIP, TEX, or LATEX file.')
    return redirect(url_for('index'))

def process_latex_zip(zip_path):
    """Extract and convert LaTeX files from zip"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract zip
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find LaTeX files - prioritize main.tex
        latex_files = []
        main_tex = None
        
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file.endswith(('.tex', '.latex')) and not file.startswith('.'):
                    full_path = os.path.join(root, file)
                    if file.lower() == 'main.tex':
                        main_tex = full_path
                    else:
                        latex_files.append(full_path)
        
        # If main.tex exists, only process that
        if main_tex:
            latex_files = [main_tex]
        
        if not latex_files:
            raise Exception("No LaTeX files found in the zip archive")
        
        # Create output directory
        output_name = os.path.splitext(os.path.basename(zip_path))[0]
        output_dir = os.path.join(OUTPUT_FOLDER, output_name)
        os.makedirs(output_dir, exist_ok=True)
        
        # Convert each LaTeX file
        for latex_file in latex_files:
            base_name = os.path.splitext(os.path.basename(latex_file))[0]
            html_path = os.path.join(output_dir, f"{base_name}.html")
            
            try:
                convert_latex_to_html(latex_file, html_path)
                if os.path.exists(html_path):
                    print(f"Successfully converted: {base_name}.html")
                else:
                    print(f"Warning: {base_name}.html was not created at {html_path}")
            except Exception as e:
                print(f"Error converting {latex_file}: {e}")
                continue
        
        return output_name

def process_single_latex_file(latex_path):
    """Process a single LaTeX file"""
    try:
        # Get absolute path
        abs_latex_path = os.path.abspath(latex_path)
        
        # Validate file exists and is readable
        if not os.path.exists(abs_latex_path):
            raise FileNotFoundError(f"File not found: {abs_latex_path}")
        
        # Create output directory
        base_name = os.path.splitext(os.path.basename(abs_latex_path))[0]
        output_dir = os.path.join(OUTPUT_FOLDER, base_name)
        os.makedirs(output_dir, exist_ok=True)
        
        # Convert LaTeX to HTML
        html_path = os.path.join(output_dir, f"{base_name}.html")
        
        try:
            convert_latex_to_html(abs_latex_path, html_path)
            if os.path.exists(html_path):
                enhance_html_accessibility(html_path)
                print(f"Successfully converted: {base_name}.html")
            else:
                raise Exception(f"HTML file was not created at {html_path}")
        except Exception as e:
            raise Exception(f"Error converting {abs_latex_path}: {str(e)}")
        
        return base_name
        
    except Exception as e:
        raise Exception(f"Failed to process LaTeX file: {str(e)}")

@app.route('/download/<path:filename>')
def download_file(filename):
    # Create a zip file of the output directory
    output_dir = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(output_dir):
        zip_path = f"{output_dir}.zip"
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, output_dir)
                    zipf.write(file_path, arcname)
        return send_file(zip_path, as_attachment=True)
    else:
        flash('Output files not found')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)
