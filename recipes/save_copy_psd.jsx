// 配方：save_copy_psd
// 用途：把带全部图层的文档另存一份 PSD 副本（交付可编辑成果；源文档不改指向、不覆盖）。
// 参数：
//   doc_id   int   默认=当前文档
//   path     str   必填   新路径，必须以 .psd 结尾且文件不存在；缺目录会自动建
// 产出：一个 PSD 文件（图层、蒙版、Alpha 通道、ICC 都保留）
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分；PSD 上限 30000 px / 2 GB，超出要改存 PSB（本配方不处理）。

function run(args) {
  var doc = getDoc(args);
  var path = opt(args, 'path', '');
  if (!path) fail('BAD_ARG', 'path 必填（新路径）');
  if (!/\.psd$/.test(path)) fail('BAD_ARG', 'path 必须以小写 .psd 结尾：' + path);
  var f = new File(path);
  if (f.exists) fail('OUTPUT_EXISTS', '文件已存在，换个新路径：' + path);
  if (!f.parent.exists && !f.parent.create()) fail('DIR_CREATE_FAILED', f.parent.fsName);
  var o = new PhotoshopSaveOptions();
  o.layers = true; o.embedColorProfile = true; o.alphaChannels = true; o.annotations = true; o.spotColors = true;
  doc.saveAs(f, o, true, Extension.LOWERCASE);
  if (!new File(path).exists) fail('SAVE_FAILED', '保存后没找到文件：' + path);
  return { path: f.fsName, doc_id: doc.id, layer_count: doc.layers.length, bytes: new File(path).length };
}
