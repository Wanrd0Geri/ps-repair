// 配方：select_polygon
// 用途：建多边形（套索）选区，适合沿屋檐、山脊等斜边圈瑕疵。
// 参数：
//   doc_id       int              默认=当前文档
//   points       [[x,y],...]      必填   至少 3 个点，按顺序连成闭合多边形
//   mode         str              默认="replace"   replace/add/subtract/intersect
//   feather      number           默认=0
//   anti_alias   bool             默认=true
// 产出：选区；返回 bounds
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分。

function run(args) {
  var doc = getDoc(args);
  var pts = opt(args, 'points', null);
  if (!(pts instanceof Array) || pts.length < 3) fail('BAD_ARG', 'points 至少 3 个 [x,y]');
  doc.selection.select(pts, selType(opt(args, 'mode', 'replace')), Number(opt(args, 'feather', 0)), !!opt(args, 'anti_alias', true));
  if (!hasSelection(doc)) fail('EMPTY_SELECTION', '多边形面积为 0');
  return { bounds: selBounds(doc) };
}
