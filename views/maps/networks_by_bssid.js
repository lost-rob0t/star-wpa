function(doc) {
  if (!valid(doc) || doc.dtype !== 'wireless-network' || typeof doc.bssid !== 'string') return;
  emit([doc.dataset, doc.bssid], doc.id);
}
