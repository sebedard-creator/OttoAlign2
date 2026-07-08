import os
import glob
import uuid
import zipfile
import tempfile
import subprocess
import threading
from flask import Flask, request, send_file, render_template, jsonify

app = Flask(__name__, static_folder='static', static_url_path='', template_folder='static')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
app.config['MAX_CONTENT_LENGTH'] = 2000 * 1024 * 1024  # 2000 MB max

jobs = {}

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'error': 'Les fichiers sont trop volumineux (limite: 2 Go).'}), 413

@app.route('/')
def index():
    return render_template('index.html')

def background_process(job_id, ref_zip, tgt_zip, job_dir):
    try:
        ref_dir = os.path.join(job_dir, 'reference')
        tgt_dir = os.path.join(job_dir, 'target')
        os.makedirs(ref_dir, exist_ok=True)
        os.makedirs(tgt_dir, exist_ok=True)
        output_aaf_path = os.path.join(job_dir, 'output.aaf')
        log_file_path = os.path.join(job_dir, 'process.log')
        
        with open(log_file_path, 'a') as f:
            f.write("Extraction des archives...\n")
            
        with zipfile.ZipFile(ref_zip, 'r') as z: z.extractall(ref_dir)
        with zipfile.ZipFile(tgt_zip, 'r') as z: z.extractall(tgt_dir)
            
        ref_aafs = glob.glob(os.path.join(ref_dir, '**', '*.aaf'), recursive=True)
        tgt_aafs = glob.glob(os.path.join(tgt_dir, '**', '*.aaf'), recursive=True)
        
        ref_aafs = [f for f in ref_aafs if not os.path.basename(f).startswith('._')]
        tgt_aafs = [f for f in tgt_aafs if not os.path.basename(f).startswith('._')]
        
        if not ref_aafs or not tgt_aafs:
            raise Exception("Missing .aaf file in one of the ZIP archives.")
            
        ref_audio_dirs = glob.glob(os.path.join(ref_dir, '**', 'Audio Files'), recursive=True)
        tgt_audio_dirs = glob.glob(os.path.join(tgt_dir, '**', 'Audio Files'), recursive=True)
        
        if not ref_audio_dirs or not tgt_audio_dirs:
            raise Exception("Missing 'Audio Files' directory in one of the ZIP archives.")
            
        with open(log_file_path, 'a') as f:
            f.write("Lancement du moteur d'alignement (cela peut prendre du temps)...\n")
            
        cmd = [
            'python', '-u', 'align_engine.py', 
            ref_aafs[0], ref_audio_dirs[0],
            tgt_aafs[0], tgt_audio_dirs[0],
            output_aaf_path
        ]
        
        with open(log_file_path, 'a') as f:
            process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, text=True)
            process.wait()
            if process.returncode != 0:
                raise Exception("Alignment engine failed. Check logs.")
                
        with open(log_file_path, 'a') as f:
            f.write("\nLancement du nettoyage et formatage final...\n")
        
        final_aaf_path = os.path.join(job_dir, 'final_aligned.aaf')
        cmd2 = ['python', '-u', 'orchestrator.py', output_aaf_path, final_aaf_path]
        
        with open(log_file_path, 'a') as f:
            process2 = subprocess.Popen(cmd2, stdout=f, stderr=subprocess.STDOUT, text=True)
            process2.wait()
            if process2.returncode != 0:
                raise Exception("Orchestrator engine failed. Check logs.")
                
        if not os.path.exists(final_aaf_path):
            raise Exception("Alignment or Un-rendering failed.")
            
        with open(log_file_path, 'a') as f:
            f.write("\nCompression du fichier de résultat...\n")
            
        final_zip_path = os.path.join(job_dir, 'OttoAligned_Result.zip')
        with zipfile.ZipFile(final_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(final_aaf_path, arcname='OttoAligned.aaf')
            aligned_wavs = glob.glob(os.path.join(tgt_audio_dirs[0], '*_ottoaligned.wav'))
            for wav in aligned_wavs:
                arcname = os.path.join('Audio Files', os.path.basename(wav))
                zf.write(wav, arcname=arcname)
                
        with open(log_file_path, 'a') as f:
            f.write("\nNettoyage des fichiers temporaires...\n")
            
        import shutil
        try:
            shutil.rmtree(ref_dir)
            shutil.rmtree(tgt_dir)
            os.remove(ref_zip)
            os.remove(tgt_zip)
            os.remove(output_aaf_path)
            os.remove(final_aaf_path)
        except Exception as e:
            with open(log_file_path, 'a') as f:
                f.write(f"Warning: Erreur lors du nettoyage: {e}\n")
                
        with open(log_file_path, 'a') as f:
            f.write("Terminé avec succès !\n")
            
        jobs[job_id]['status'] = 'done'
        jobs[job_id]['zip_path'] = final_zip_path
        
    except Exception as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['message'] = str(e)
        log_file_path = os.path.join(job_dir, 'process.log')
        if os.path.exists(log_file_path):
            with open(log_file_path, 'a') as f:
                f.write(f"\nErreur critique: {str(e)}\n")

@app.route('/api/process', methods=['POST'])
def process_align():
    if 'ref_file' not in request.files or 'tgt_file' not in request.files:
        return jsonify({'error': 'Missing reference or target file'}), 400
    
    ref_file = request.files['ref_file']
    tgt_file = request.files['tgt_file']
    
    if not ref_file.filename.lower().endswith('.zip') or not tgt_file.filename.lower().endswith('.zip'):
        return jsonify({'error': 'Only ZIP files are supported'}), 400

    job_id = str(uuid.uuid4())
    job_dir = os.path.join(app.config['UPLOAD_FOLDER'], f'ottoalign_{job_id}')
    os.makedirs(job_dir, exist_ok=True)
    
    ref_zip = os.path.join(job_dir, 'ref.zip')
    tgt_zip = os.path.join(job_dir, 'tgt.zip')
    
    ref_file.save(ref_zip)
    tgt_file.save(tgt_zip)
    
    jobs[job_id] = {'status': 'processing', 'job_dir': job_dir}
    
    thread = threading.Thread(target=background_process, args=(job_id, ref_zip, tgt_zip, job_dir))
    thread.start()
    
    return jsonify({'job_id': job_id})

@app.route('/api/status/<job_id>')
def job_status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
        
    job = jobs[job_id]
    log_content = ""
    if 'job_dir' in job:
        log_path = os.path.join(job['job_dir'], 'process.log')
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                log_content = f.read()
                
    # Keep only the last 50 lines to avoid massive payloads
    lines = log_content.split('\n')
    if len(lines) > 50:
        lines = lines[-50:]
        log_content = "... (logs précédents masqués) ...\n" + '\n'.join(lines)
                
    return jsonify({
        'status': job['status'],
        'log': log_content,
        'message': job.get('message', '')
    })

@app.route('/api/download/<job_id>')
def download_result(job_id):
    if job_id not in jobs or jobs[job_id]['status'] != 'done':
        return "Not ready", 400
    return send_file(
        jobs[job_id]['zip_path'], 
        as_attachment=True, 
        download_name='OttoAligned_Result.zip',
        mimetype='application/zip'
    )

@app.route('/api/clear_cache', methods=['DELETE'])
def clear_cache():
    try:
        deleted_count = 0
        temp_dir = app.config['UPLOAD_FOLDER']
        if os.path.exists(temp_dir):
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith('.zip'):
                        os.remove(os.path.join(root, file))
                        deleted_count += 1
        return jsonify({'success': True, 'deleted': deleted_count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting OttoAlign2 Web UI on port 8081...")
    app.run(host='0.0.0.0', port=8081, debug=False)
