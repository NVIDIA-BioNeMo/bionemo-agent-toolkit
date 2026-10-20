// Build-time adaptation of the pinned public Studio file controller.
// Keep upstream source unchanged; these hooks enforce embedded draft ownership.
export function adaptSessionFileController(s, bridge) {
  function replaceOnce(s, from, to) {
    if (s.split(from).length !== 2) throw Error(`Upstream hook changed: ${from}`);
    return s.replace(from, to);
  }
      s = `import {nativeFileNavigation, downloadFile} from ${JSON.stringify(bridge)};\n` + s;
      s = replaceOnce(s, 'onOpened: (response: SessionResponse) => Promise<void>;', 'onOpened: (response: SessionResponse, current?: () => boolean, beginCommit?: () => void) => Promise<void>;');
      s = replaceOnce(s, '  private openFile(file: File, targetSession: string | null = null): Promise<boolean> {', `  private openFile(file: File, targetSession: string | null = null): Promise<boolean> {
    return nativeFileNavigation(request => this.openFileInternal(file, request, targetSession), {freshDocument:targetSession === null}).catch(error => { this.options.log(String(error)); return false; });
  }
  private openFileInternal(file: File, navigation: any, targetSession: string | null = null): Promise<boolean> {`);
      s = replaceOnce(s, '  private async loadExample(', `  private async loadExample(example: StudioExample, activeButton: HTMLButtonElement): Promise<void> {
    try { await nativeFileNavigation(request => this.loadExampleInternal(example, activeButton, request), {freshDocument:true}); }
    catch(error) { this.options.log(String(error)); }
  }
  private async loadExampleInternal(`);
      s = replaceOnce(s, 'const loaded = await this.openFile(', 'const loaded = await this.openFileInternal(');
      s = replaceOnce(s, '  private async combineFile(): Promise<void> {', `  private async combineFile(): Promise<void> {
    try { await nativeFileNavigation(request => this.combineFileInternal(request)); }
    catch(error) { this.options.log(String(error)); }
  }
  private async combineFileInternal(request: any): Promise<void> {`);
      s = replaceOnce(s, 'this.performOpen(file, generation, targetSession)', 'this.performOpen(file, generation, targetSession, navigation)');
      s = replaceOnce(s, 'private async performOpen(file: File, generation: number, targetSession: string | null)', 'private async performOpen(file: File, generation: number, targetSession: string | null, request: any)');
      s = replaceOnce(s, 'const isCurrent = () => generation === this.openGeneration', 'const isCurrent = () => request.current() && generation === this.openGeneration');
      s = replaceOnce(s, 'this.prepareImport(file, isCurrent)', 'this.prepareImport(file, isCurrent, request.signal)');
      s = replaceOnce(s, 'private async prepareImport(file: File, isCurrent: () => boolean)', 'private async prepareImport(file: File, isCurrent: () => boolean, signal: AbortSignal)');
      s = replaceOnce(s, 'this.chooseImportOptions(inspection.message, form)', 'this.chooseImportOptions(inspection.message, form, signal)');
      s = replaceOnce(s, 'private chooseImportOptions(message: string, form: FormData)', 'private chooseImportOptions(message: string, form: FormData, signal: AbortSignal)');
      s = replaceOnce(s, '      this.importDialog = dialog;', `      this.importDialog = dialog;
      const cancelImport = () => { if (this.importDialog === dialog) dialog.close('cancel'); };
      signal.addEventListener('abort', cancelImport, {once:true});`);
      s = replaceOnce(s, '        parent.append(settings);', `        signal.removeEventListener('abort', cancelImport);
        if (this.importDialog !== dialog) { dialog.remove(); resolve(false); return; }
        parent.append(settings);`);
      s = replaceOnce(s, '      dialog.showModal();', `      dialog.showModal();
      if (signal.aborted) cancelImport();`);
      s = replaceOnce(s, 'await this.options.onOpened(response);', 'await this.options.onOpened(response, request.current, request.beginCommit);');
      s = replaceOnce(s, '    activeButton: HTMLButtonElement,', '    activeButton: HTMLButtonElement,\n    request: any,');
      s = replaceOnce(s, 'example.file, { type: "chemical/x-mmcif" }),', 'example.file, { type: "chemical/x-mmcif" }), request,');
      s = replaceOnce(s, '      const combined = await api<SessionResponse>(`/api/sessions/${targetSession}/combine`, {', '      const copySession = await request.copySavedSession();\n      const combined = await api<SessionResponse>(`/api/sessions/${copySession}/combine`, {');
      s = replaceOnce(s, 'await this.openFile(file, targetSession);', 'await this.openFileInternal(file, request, targetSession);');
      s = replaceOnce(s, 'await this.options.onCombined(combined, file.name);', 'await this.options.onOpened(combined, request.current, request.beginCommit);');
      s = replaceOnce(s, `      const blob = new Blob([result.cif], { type: "chemical/x-mmcif" });
      const anchor = document.createElement("a");
      anchor.href = URL.createObjectURL(blob);
      anchor.download = \`\${result.name}_annotated.cif\`;
      anchor.click();
      URL.revokeObjectURL(anchor.href);`, '      await downloadFile({filename:result.name + "_annotated.cif", mimeType:"chemical/x-mmcif", text:result.cif});');
  return s;
}
