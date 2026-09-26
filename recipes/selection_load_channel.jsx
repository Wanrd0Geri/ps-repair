// 配方：selection_load_channel
// 用途：从 Alpha 通道载入选区（可与当前选区相加/相减/相交）。
// 参数：
//   doc_id   int    默认=当前文档
//   name     str    必填   通道名
//   mode     str    默认="replace"   replace/add/subtract/intersect
//   invert   bool   默认=false       载入时反相
// 产出：选区；返回 bounds
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分。

function run(args) {
  var doc = getDoc(args);
  var name = opt(args, 'name', '');
  var ch = findChannel(doc, name);
  if (!ch) fail('CHANNEL_NOT_FOUND', '没有名为「' + name + '」的通道');
  doc.selection.load(ch, selType(opt(args, 'mode', 'replace')), !!opt(args, 'invert', false));
  return { bounds: selBounds(doc) };
}
