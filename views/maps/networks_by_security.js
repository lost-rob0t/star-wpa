function(doc) {
  if (!valid(doc) || doc.dtype !== 'wireless-network' || typeof doc.security !== 'string') return;
  emit([doc.dataset, doc.security], doc.id);
}
