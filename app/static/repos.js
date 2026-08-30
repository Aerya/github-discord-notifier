(() => {
  const search=document.getElementById('repo-search'); const cards=[...document.querySelectorAll('.repo-card')]; let filter='all';
  const apply=()=>{const q=(search?.value||'').trim().toLowerCase(); cards.forEach(c=>{const ok=c.dataset.name.includes(q)&&(filter==='all'||c.dataset.selected==='1'); c.style.display=ok?'':'none';});};
  search?.addEventListener('input',apply); document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;apply();}));
  cards.forEach(c=>{const m=c.querySelector('input[name="selected"]'); m?.addEventListener('change',()=>c.dataset.selected=m.checked?'1':'0');});
})();
