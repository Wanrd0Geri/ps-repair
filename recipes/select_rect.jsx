// 配方：select_rect
// 用途：建矩形选区（像素坐标，左上角为原点）。
// 参数：
//   doc_id    int          默认=当前文档
//   rect      [l,t,r,b]    必填   right/bottom 不含（[0,0,10,10] 是 10×10）
//   mode      str          默认="replace"   replace/add/subtract/intersect
//   feather   number       默认=0           选区羽化像素（改选区本身；想可逆请用蒙版羽化）
// 产出：选区；返回 bounds
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分；不抗锯齿，边界落在整像素上。

function run(args) {
  var doc = getDoc(args);
  doc.selection.select(rectPoints(opt(args, 'rect', null)), selType(opt(args, 'mode', 'replace')), Number(opt(args, 'feather', 0)), false);
  return { bounds: selBounds(doc) };
}
