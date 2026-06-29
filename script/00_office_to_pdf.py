#!/usr/bin/env python
# Auto-generated from 00_office_to_pdf.ipynb

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _os.path.dirname(_HERE))  # import utils_cc from parent (customChunkPipeline)
_os.chdir(_os.path.dirname(_HERE))       # run as if from customChunkPipeline/

import os, shutil, subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('../.env', override=True)  # ./.env (project root)
load_dotenv(override=True)  # local .env overrides if present

DATA_DIR = Path('../data')   # ソースドキュメント
PDF_DIR  = Path('./pdf')     # 処理対象の PDF 置き場
PDF_DIR.mkdir(parents=True, exist_ok=True)
print('data files:', [p.name for p in DATA_DIR.iterdir()] if DATA_DIR.exists() else 'NO data dir')

def find_soffice():
    for name in ('soffice', 'soffice.exe', 'libreoffice'):
        path = shutil.which(name)
        if path:
            return path
    # Common Windows install locations
    for cand in (r'C:\Program Files\LibreOffice\program\soffice.exe',
                 r'C:\Program Files (x86)\LibreOffice\program\soffice.exe'):
        if Path(cand).exists():
            return cand
    return None

def office_to_pdf_soffice(soffice, src_path, out_dir):
    # LibreOffice auto-detects the document type; works for xlsx/pptx/docx.
    subprocess.run([soffice, '--headless', '--convert-to', 'pdf',
                    '--outdir', str(out_dir), str(src_path)], check=True)

def excel_to_pdf_com(xlsx_path, pdf_path):
    # Windows + Microsoft Excel only
    import win32com.client as win32
    excel = win32.DispatchEx('Excel.Application')
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        wb = excel.Workbooks.Open(str(xlsx_path.resolve()))
        # 0 = xlTypePDF
        wb.ExportAsFixedFormat(0, str(pdf_path.resolve()))
        wb.Close(False)
    finally:
        excel.Quit()

def ppt_to_pdf_com(ppt_path, pdf_path):
    # Windows + Microsoft PowerPoint only
    import win32com.client as win32
    ppt = win32.DispatchEx('PowerPoint.Application')
    try:
        pres = ppt.Presentations.Open(str(ppt_path.resolve()), WithWindow=False)
        # 32 = ppSaveAsPDF
        pres.SaveAs(str(pdf_path.resolve()), 32)
        pres.Close()
    finally:
        ppt.Quit()

def word_to_pdf_com(doc_path, pdf_path):
    # Windows + Microsoft Word only
    import win32com.client as win32
    word = win32.DispatchEx('Word.Application')
    word.Visible = False
    try:
        d = word.Documents.Open(str(doc_path.resolve()), ReadOnly=True)
        # 17 = wdFormatPDF
        d.SaveAs(str(pdf_path.resolve()), FileFormat=17)
        d.Close(False)
    finally:
        word.Quit()

soffice = find_soffice()
print('LibreOffice:', soffice or 'not found (will try Office COM on Windows)')

for src in sorted(DATA_DIR.iterdir()):
    if src.suffix.lower() == '.pdf':
        dst = PDF_DIR / src.name
        shutil.copy2(src, dst)
        print('copied PDF :', src.name)
    elif src.suffix.lower() in ('.xlsx', '.xls'):
        pdf_path = PDF_DIR / (src.stem + '.pdf')
        if soffice:
            office_to_pdf_soffice(soffice, src, PDF_DIR)
        else:
            excel_to_pdf_com(src, pdf_path)
        print('converted  :', src.name, '->', pdf_path.name)
    elif src.suffix.lower() in ('.pptx', '.ppt'):
        pdf_path = PDF_DIR / (src.stem + '.pdf')
        if soffice:
            office_to_pdf_soffice(soffice, src, PDF_DIR)
        else:
            ppt_to_pdf_com(src, pdf_path)
        print('converted  :', src.name, '->', pdf_path.name)
    elif src.suffix.lower() in ('.docx', '.doc'):
        pdf_path = PDF_DIR / (src.stem + '.pdf')
        if soffice:
            office_to_pdf_soffice(soffice, src, PDF_DIR)
        else:
            word_to_pdf_com(src, pdf_path)
        print('converted  :', src.name, '->', pdf_path.name)

print('\nPDF dir now contains:', [p.name for p in PDF_DIR.glob('*.pdf')])
