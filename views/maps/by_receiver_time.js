function(doc) {
  if (!valid(doc) || doc.dtype !== 'event') return;
  var w = doc.extensions && doc.extensions['org.starintel/wpa@1'];
  if (!w || typeof w.receiverId !== 'string' || !w.receiverId || !time(doc.observedAt)) return;
  emit([doc.dataset, w.receiverId, doc.observedAt], doc.id);
}
