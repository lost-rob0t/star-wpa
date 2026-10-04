function(doc) {
  if (!valid(doc) || doc.dtype !== 'event' || doc.eventKind !== 'wireless-sighting') return;
  var w = doc.extensions && doc.extensions['org.starintel/wpa@1'];
  if (!sighting(w, doc) || !positioned(w)) return;
  if (!(typeof w.distanceMeters === 'number' && isFinite(w.distanceMeters) && w.distanceMeters > 0) &&
      !(typeof w.signalDbm === 'number' && isFinite(w.signalDbm))) return;
  emit([doc.dataset, w.networkId, Math.floor(doc.observedAt / 10)], reading(doc, w));
}
