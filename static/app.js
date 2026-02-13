async function getStatus() {
  const res = await fetch('/api/status');
  const data = await res.json();
  for (const key of ['status', 'progress', 'speed', 'eta', 'last_log', 'error', 'command']) {
    const el = document.getElementById(key);
    if (el) el.textContent = data[key] || '-';
  }
}

async function startDownload() {
  const formData = new FormData();
  formData.append('torrent_url', document.getElementById('torrent_url').value.trim());
  formData.append('download_dir', document.getElementById('download_dir').value.trim());
  const fileInput = document.getElementById('torrent_file');
  if (fileInput.files.length > 0) {
    formData.append('torrent_file', fileInput.files[0]);
  }

  const res = await fetch('/api/start', { method: 'POST', body: formData });
  const data = await res.json();
  alert(data.message);
  await getStatus();
}

async function stopDownload() {
  const res = await fetch('/api/stop', { method: 'POST' });
  const data = await res.json();
  alert(data.message);
  await getStatus();
}

document.getElementById('start_btn').addEventListener('click', startDownload);
document.getElementById('stop_btn').addEventListener('click', stopDownload);

setInterval(getStatus, 1200);
getStatus();
