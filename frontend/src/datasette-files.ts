let _loaded = false;

export function ensureFilePickerLoaded() {
  if (_loaded || customElements.get('datasette-file-picker')) {
    _loaded = true;
    return;
  }
  _loaded = true;
  const script = document.createElement('script');
  script.type = 'module';
  script.src = '/-/static-plugins/datasette_files/datasette-file-picker.js';
  document.head.appendChild(script);
}
