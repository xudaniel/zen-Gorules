export const base = { cargo:'none', containment:true, atmosphere:'oxygen', suit:true, telepathy:false, consent:true, translator:true, days:7, purpose:'tourism' };
export const travelers = [
 {name:'Bloop',zh:'布噜',planet:'Kepler-186f',role:['First-time tourist','第一次来地球的游客'],quote:['“I have traveled 500 light-years to meet a duck.”','“我飞了 500 光年，就是想见一只鸭子。”'],color:'#b9d995',case:{...base}},
 {name:'Pell',zh:'佩尔',planet:'Titan',role:['Interstellar poet','星际诗人'],quote:['“The black hole is emotional support. It is very small.”','“这个黑洞是我的精神支柱。它很小的。”'],color:'#c5b9e8',case:{...base,atmosphere:'methane',cargo:'blackHole',purpose:'culture'}},
 {name:'Ambassador IX',zh:'九号大使',planet:'Gliese 581g',role:['Diplomatic delegation','外交代表'],quote:['“I already know what you are thinking. Lovely planet.”','“我已经知道你在想什么。好漂亮的星球。”'],color:'#efb187',case:{...base,telepathy:true,consent:false,purpose:'diplomacy'}},
 {name:'Moss',zh:'苔苔',planet:'TRAPPIST-1e',role:['Enthusiastic botanist','热情的植物学家'],quote:['“A gift for your gardens. They only glow at night.”','“送给你们花园的礼物。它们只在夜里发光。”'],color:'#93caca',case:{...base,cargo:'spores',containment:false,purpose:'culture',days:14}}
];
export function validate(input) {
 const enums={cargo:['none','stardust','spores','blackHole'],atmosphere:['oxygen','methane','vacuum'],purpose:['tourism','culture','diplomacy']};
 for(const [key,values] of Object.entries(enums)) if(!values.includes(input[key])) throw new Error('Invalid '+key);
 for(const key of ['containment','suit','telepathy','consent','translator']) if(typeof input[key]!=='boolean') throw new Error('Invalid '+key);
 if(!Number.isInteger(input.days)||input.days<1||input.days>90) throw new Error('Visit must be 1–90 whole days');
 return input;
}
