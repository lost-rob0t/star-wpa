function(doc) {
  if (!valid(doc) || doc.dtype !== 'wireless-station' || typeof doc.mac !== 'string') return;
  emit([doc.dataset, doc.mac], doc.id);
}
