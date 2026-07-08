document.getElementById('align-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const sourceFile = document.getElementById('ref-file').files[0];
    const targetFile = document.getElementById('tgt-file').files[0];
    
    if (!sourceFile || !targetFile) return;

    const btn = document.getElementById('render-btn');
    const btnText = btn.querySelector('.btn-text');
    const loader = btn.querySelector('.loader');
    const statusMsg = document.getElementById('status-message');

    const loadingDiv = document.getElementById('loading');

    // UI Loading state
    btn.disabled = true;
    btnText.classList.add('hidden');
    loader.classList.remove('hidden');
    loadingDiv.style.display = 'block';
    statusMsg.classList.remove('hidden', 'error', 'success');
    statusMsg.textContent = 'Téléchargement et analyse en cours...';

    const formData = new FormData();
    formData.append('ref_file', sourceFile);
    formData.append('tgt_file', targetFile);

    const resetUI = () => {
        btn.disabled = false;
        btnText.classList.remove('hidden');
        loader.classList.add('hidden');
        loadingDiv.style.display = 'none';
    };

    try {
        const response = await fetch('/api/process', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Erreur lors du traitement');
        }
        
        const jobId = data.job_id;
        const logBox = document.getElementById('log-box');
        logBox.innerText = "Démarrage de la tâche...";
        
        // Poll status every 2 seconds
        const pollInterval = setInterval(async () => {
            try {
                const statusRes = await fetch('/api/status/' + jobId);
                const statusData = await statusRes.json();
                
                if (statusData.log) {
                    logBox.innerText = statusData.log;
                    logBox.scrollTop = logBox.scrollHeight;
                }
                
                if (statusData.status === 'done') {
                    clearInterval(pollInterval);
                    resetUI();
                    statusMsg.textContent = 'Traitement terminé ! Téléchargement en cours...';
                    statusMsg.classList.add('success');
                    
                    const url = '/api/download/' + jobId;
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'OttoAligned_Result.zip';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    
                } else if (statusData.status === 'error') {
                    clearInterval(pollInterval);
                    resetUI();
                    statusMsg.textContent = statusData.message || 'Erreur inconnue';
                    statusMsg.classList.add('error');
                }
            } catch (err) {
                clearInterval(pollInterval);
                resetUI();
                statusMsg.textContent = err.message;
                statusMsg.classList.add('error');
            }
        }, 2000);

    } catch (error) {
        resetUI();
        statusMsg.textContent = error.message;
        statusMsg.classList.add('error');
    }
});

document.getElementById('clear-cache-btn').addEventListener('click', async () => {
    if (confirm("Voulez-vous vraiment supprimer tous les fichiers ZIP des jobs terminés ? Les logs seront conservés.")) {
        try {
            const response = await fetch('/api/clear_cache', { method: 'DELETE' });
            const data = await response.json();
            if (data.success) {
                alert(`Cache vidé avec succès ! ${data.deleted} fichier(s) supprimé(s).`);
            } else {
                alert(`Erreur : ${data.error}`);
            }
        } catch (e) {
            alert(`Erreur de connexion : ${e}`);
        }
    }
});
