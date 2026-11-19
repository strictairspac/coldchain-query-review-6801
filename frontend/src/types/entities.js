/** @typedef {{id:number,name:string,description:string,original_sql:string}} Sample */
/** @typedef {{id:number,name:string,sample_id:number,candidate_sql:string,status:string}} Batch */
/** @typedef {{id:number,batch_id:number,result:Object}} Evidence */
/** @typedef {{id:number,client_key:string,customer:string,route:string|null,delta_per_invoice:string,declared_delta:string,reason:string,status:string,basis_hash:string,trial:Object,reject_reason:string|null,created_at:string,decided_at:string|null}} Correction */
export const entityNames={sample:'SQL 样本',batch:'复核批次',evidence:'执行证据',correction:'运费更正'};
