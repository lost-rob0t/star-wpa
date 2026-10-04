function(doc) {
  if (!valid(doc) || doc.dtype !== 'relation' || !ref(doc.source) || !ref(doc.destination)) return;
  emit([doc.dataset, doc.source.id, doc.predicate, doc.destination.id], doc.id);
}
