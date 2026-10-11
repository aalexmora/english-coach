(() => {
  const key='english-coach-ui-theme',media=matchMedia('(prefers-color-scheme: dark)');
  let mode='system';try{mode=localStorage.getItem(key)||mode;}catch{}
  function apply(next,persist=false){mode=['light','dark','system'].includes(next)?next:'system';document.documentElement.dataset.themeMode=mode;document.documentElement.dataset.theme=mode==='dark'||mode==='system'&&media.matches?'dark':'light';if(persist)try{localStorage.setItem(key,mode);}catch{}}
  apply(mode);media.addEventListener('change',()=>{if(mode==='system')apply(mode);});window.coachTheme=apply;
})();
