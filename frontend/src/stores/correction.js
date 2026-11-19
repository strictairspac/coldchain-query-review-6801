import{listCorrections}from'../api/correction.js';export const corrections={items:[],async load(){this.items=await listCorrections();return this.items}};
