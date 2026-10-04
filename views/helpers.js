function valid(doc) {
  return doc && typeof doc.id === 'string' && doc.id && doc.id.indexOf('_design/') !== 0 &&
    (!doc._id || doc._id === doc.id) && !doc.deleted && !doc._deleted &&
    doc.schemaVersion === '0.10.1' && typeof doc.dataset === 'string' && doc.dataset;
}
function time(t) { return typeof t === 'number' && isFinite(t) && t >= 0 && Math.floor(t) === t; }
function ref(r) { return r && typeof r.id === 'string' && typeof r.schema === 'string'; }
function decimal(d) { return typeof d === 'string' && /^[+-]?[0-9]+(?:\.[0-9]+)?$/.test(d) && isFinite(Number(d)); }
function sighting(w, doc) {
  return w && typeof w.receiverId === 'string' && w.receiverId && typeof w.bssid === 'string' && w.bssid &&
    typeof w.networkId === 'string' && w.networkId && time(doc.observedAt);
}
function positioned(w) {
  return typeof w.latitude === 'number' && isFinite(w.latitude) && Math.abs(w.latitude) <= 90 &&
    typeof w.longitude === 'number' && isFinite(w.longitude) && Math.abs(w.longitude) <= 180;
}
function reading(doc, w) {
  var r = {id: doc.id, receiverId: w.receiverId, observedAt: doc.observedAt, bssid: w.bssid, networkId: w.networkId};
  if (positioned(w)) { r.latitude = w.latitude; r.longitude = w.longitude; }
  if (typeof w.signalDbm === 'number' && isFinite(w.signalDbm)) r.signalDbm = w.signalDbm;
  if (typeof w.distanceMeters === 'number' && isFinite(w.distanceMeters)) r.distanceMeters = w.distanceMeters;
  if (typeof w.rangeAccuracyMeters === 'number' && isFinite(w.rangeAccuracyMeters)) r.rangeAccuracyMeters = w.rangeAccuracyMeters;
  return r;
}
