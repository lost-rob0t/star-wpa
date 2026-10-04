function(doc) {
  if (!valid(doc) || doc.dtype !== 'relation' || !ref(doc.source) || !ref(doc.destination)) return;
  emit([doc.dataset, doc.destination.id, doc.predicate, doc.source.id], doc.id);
}
