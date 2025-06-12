from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import openai
import time
import logging
import textwrap
from fpdf import FPDF
import os
from io import BytesIO
import json
from datetime import datetime
import re

app = Flask(__name__)
CORS(app)

# Konfigurasi
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Konfigurasi NVIDIA API
openai.api_key = "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"
openai.api_base = "https://integrate.api.nvidia.com/v1"

# Database sederhana untuk menyimpan riwayat
STORIES_DB = {}
IMAGE_PROMPTS = {
    "sabar": "Illustration of a child being patient in a difficult situation, Islamic art style, colorful, child-friendly",
    "jujur": "Child telling the truth in a difficult situation, cartoon style with warm colors",
    "sedekah": "Happy child giving charity to poor people, mosque in background, watercolor style",
    "taat orang tua": "Child helping parents with housework, loving family scene, Islamic values",
    "tidak sombong": "Humble child sharing with friends, playground setting, bright colors"
}

class IslamicStoryPDF(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 12)
        self.cell(0, 10, 'Cerita Islami untuk Anak', 0, 1, 'C')
    
    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.cell(0, 10, f'Halaman {self.page_no()}', 0, 0, 'C')

def generate_pdf(story_data):
    pdf = IslamicStoryPDF()
    pdf.add_page()
    pdf.set_left_margin(20)
    pdf.set_right_margin(20)

    # Header warna ceria tanpa emoji atau Unicode
    pdf.set_fill_color(179, 229, 252)  # biru pastel
    pdf.set_text_color(46, 125, 50)
    pdf.set_font('helvetica', 'B', 22)
    pdf.cell(0, 18, 'Cerita Islami untuk Anak', 0, 1, 'C', fill=True)
    pdf.ln(4)

    # Ornamen bintang dan bulan (pakai karakter ASCII saja)
    pdf.set_font('helvetica', '', 16)
    pdf.set_text_color(255, 202, 40)
    pdf.cell(0, 10, '*   o   *   o   *', 0, 1, 'C')
    pdf.ln(2)

    # Judul cerita
    pdf.set_fill_color(255, 249, 196)  # kuning pastel
    pdf.set_text_color(56, 142, 60)
    pdf.set_font('helvetica', 'B', 18)
    pdf.multi_cell(0, 14, story_data['judul'], 0, 'C', fill=True)
    pdf.ln(4)

    # Garis pelangi
    pdf.set_draw_color(255, 167, 38)  # oranye
    pdf.set_line_width(1.5)
    y = pdf.get_y()
    pdf.line(30, y, 180, y)
    pdf.ln(6)

    # Isi cerita dengan font ramah anak
    def render_markdown(paragraph):
        while True:
            match = re.search(r'\*\*([^*]+)\*\*', paragraph)
            if not match:
                break
            pdf.set_font('helvetica', 'B', 13)
            pdf.set_text_color(25, 118, 210)
            pdf.multi_cell(0, 9, match.group(1))
            pdf.set_font('helvetica', '', 12)
            pdf.set_text_color(56, 142, 60)
            paragraph = paragraph.replace(match.group(0), '')
        while True:
            match = re.search(r'\*([^*]+)\*', paragraph)
            if not match:
                break
            pdf.set_font('helvetica', 'I', 12)
            pdf.set_text_color(255, 152, 0)
            pdf.multi_cell(0, 9, match.group(1))
            pdf.set_font('helvetica', '', 12)
            pdf.set_text_color(56, 142, 60)
            paragraph = paragraph.replace(match.group(0), '')
        clean = paragraph.replace('*', '').strip()
        if clean:
            pdf.set_font('helvetica', '', 12)
            pdf.set_text_color(56, 142, 60)
            pdf.multi_cell(0, 9, clean)
        pdf.ln(2)

    pdf.set_font('helvetica', '', 12)
    pdf.set_text_color(56, 142, 60)
    for paragraph in story_data['isi'].split('\n\n'):
        render_markdown(paragraph)
    pdf.ln(4)

    # Ornamen bawah (pakai karakter ASCII saja)
    pdf.set_font('helvetica', '', 16)
    pdf.set_text_color(255, 202, 40)
    pdf.cell(0, 10, '*   o   *', 0, 1, 'C')
    pdf.ln(2)

    # Info anak
    pdf.set_font('helvetica', 'I', 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"Dibuat untuk: {story_data['nama_anak']}", 0, 1)
    pdf.cell(0, 8, f"Tema: {story_data['tema']}", 0, 1)
    pdf.cell(0, 8, f"Tanggal: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1)

    # Footer islami (tanpa emoji/Unicode)
    pdf.set_y(-30)
    pdf.set_font('helvetica', 'I', 10)
    pdf.set_text_color(129, 199, 132)
    pdf.cell(0, 10, '"Berbagi cerita, menanam akhlak mulia"', 0, 0, 'C')

    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_buffer = BytesIO(pdf_bytes)
    pdf_buffer.seek(0)
    return pdf_buffer

def generate_image_prompt(story, tema, language):
    prompt = f"Children's book illustration style, Islamic values, {IMAGE_PROMPTS.get(tema, '')}. "
    prompt += f"The story is about: {story[:200]}"  # Ambil sebagian cerita sebagai konteks
    return prompt

def generate_story(nama_anak, tema, language, age_group, length):
    start_time = time.time()
    
    # Template berdasarkan kelompok usia
    age_templates = {
        "3-5": "Gunakan kalimat sangat pendek (3-5 kata), banyak repetisi, fokus pada satu nilai moral",
        "6-8": "Gunakan kalimat sederhana (5-8 kata), sertakan dialog sederhana, tambahkan elemen fantasi",
        "9-12": "Bisa lebih kompleks, sertakan konflik moral, tambahkan quotes dari Quran/Hadits"
    }
    
    # Template berdasarkan panjang
    length_templates = {
        "pendek": "2-3 paragraf (100-150 kata)",
        "sedang": "4-5 paragraf (200-250 kata)",
        "panjang": "6-8 paragraf (300-400 kata)"
    }
    
    prompt = f"""Buat cerita Islami untuk anak dengan ketentuan:
- Nama anak: {nama_anak}
- Usia: {age_group} tahun ({age_templates.get(age_group.split('-')[0], '')}
- Panjang: {length_templates.get(length, '')}
- Tema: {tema}
- Bahasa: {'Indonesia' if language == 'id' else 'English'}
- Nilai Islami: Sertakan 1 ayat Quran atau Hadits pendek yang relevan
- Struktur:
  1. Perkenalkan karakter dan setting
  2. Hadirkan tantangan/konflik
  3. Selesaikan dengan nilai Islami
  4. Pesan moral dan doa singkat
- Gaya:
  * {age_templates.get(age_group.split('-')[0], '')}
  * Gunakan dialog interaktif
  * Tambahkan unsur keajaiban/kebaikan
  * Akhiri dengan pertanyaan reflektif

Contoh akhir:
[Pesan Moral]
[Doa Singkat]
[Pertanyaan untuk Diskusi]"""
    
    try:
        # Generate cerita
        response = openai.ChatCompletion.create(
            model="nvidia/llama-3.3-nemotron-super-49b-v1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
            top_p=0.9
        )
        story_content = response.choices[0].message['content']
        
        # Generate judul
        title_prompt = f"Buat judul 5-7 kata untuk cerita {tema} anak {age_group} tahun, bahasa {'Indonesia' if language == 'id' else 'English'}"
        title_response = openai.ChatCompletion.create(
            model="nvidia/llama-3.3-nemotron-super-49b-v1",
            messages=[{"role": "user", "content": title_prompt}],
            temperature=0.7,
            max_tokens=30
        )
        title = title_response.choices[0].message['content'].strip('"')
        
        # Generate gambar (simulasi)
        image_prompt = generate_image_prompt(story_content, tema, language)
        
        # Simpan ke database
        story_id = f"story_{int(time.time())}"
        STORIES_DB[story_id] = {
            "id": story_id,
            "judul": title,
            "isi": story_content,
            "image_prompt": image_prompt,
            "metadata": {
                "nama_anak": nama_anak,
                "tema": tema,
                "bahasa": language,
                "usia": age_group,
                "panjang": length,
                "waktu": datetime.now().isoformat(),
                "durasi_generasi": time.time() - start_time
            }
        }
        
        return STORIES_DB[story_id]
    
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            "error": str(e),
            "judul": f"Cerita {tema} untuk {nama_anak}",
            "isi": f"Maaf, terjadi kesalahan saat membuat cerita. Silakan coba lagi.\nError: {str(e)}"
        }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate_story', methods=['POST'])
def handle_generate():
    data = request.json
    required = ['nama_anak', 'tema', 'bahasa', 'usia', 'panjang']
    
    if not all(field in data for field in required):
        return jsonify({"error": "Data tidak lengkap"}), 400
    
    story = generate_story(
        nama_anak=data['nama_anak'],
        tema=data['tema'],
        language=data['bahasa'],
        age_group=data['usia'],
        length=data['panjang']
    )
    
    return jsonify(story)

@app.route('/download_pdf/<story_id>', methods=['GET'])
def download_pdf(story_id):
    if story_id not in STORIES_DB:
        return jsonify({"error": "Cerita tidak ditemukan"}), 404
    
    story = STORIES_DB[story_id]
    pdf_buffer = generate_pdf({
        "judul": story['judul'],
        "isi": story['isi'],
        "nama_anak": story['metadata']['nama_anak'],
        "tema": story['metadata']['tema']
    })
    
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"cerita_{story['metadata']['nama_anak']}_{story_id[:6]}.pdf"
    )

@app.route('/stories', methods=['GET'])
def list_stories():
    return jsonify({
        "count": len(STORIES_DB),
        "stories": list(STORIES_DB.values())
    })

if __name__ == '__main__':
    os.makedirs('stories', exist_ok=True)
    app.run(debug=True, port=5000)