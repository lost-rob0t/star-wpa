function(doc) {
  if (!valid(doc) || doc.dtype !== 'event' || doc.eventKind !== 'wireless-sighting') return;
  var w = doc.extensions && doc.extensions['org.starintel/wpa@1'];
  if (!sighting(w, doc)) return;
  emit([doc.dataset, w.networkId, doc.observedAt, w.receiverId], reading(doc, w));
}
