// Run from FPV-wave-g09/web, using the existing dependencies; no browser/network needed.
import {pathToFileURL} from 'node:url';
const {createServer}=await import(pathToFileURL(`${process.cwd()}/node_modules/vite/dist/node/index.js`).href);
const server=await createServer({configFile:false,server:{middlewareMode:true},appType:'custom'});
try{
 const {initPhysics}=await server.ssrLoadModule('/src/physics/world.ts');await initPhysics();
 const {GameSession}=await server.ssrLoadModule('/src/game/session.ts');
 const {saveRecord}=await server.ssrLoadModule('/src/game/records.ts');
 const s=new GameSession();s.start();
 function cross(x,y,z){s.world.setInitial([x-.05,y,z],[8,0,0]);for(let i=0;i<4;i++)s.step({throttle:0,roll:0,pitch:0,yaw:0});}
 cross(10,0,2.1);
 s.world.setInitial([221,0,10],[0,0,0]);s.step({throttle:0,roll:0,pitch:0,yaw:0});
 const failed={state:s.state,reason:s.reason,valid:s.snapshot().courseValid,gate:s.course.next};
 s.pause();for(const [x,y,z] of [[23,-4,2.6],[36,1,3.1],[50,6,2.6],[65,0,2.1]])cross(x,y,z);
 const map=new Map();const stored=saveRecord({getItem:k=>map.get(k)??null,setItem:(k,v)=>map.set(k,v)},s.physicsModel,s.assembly,{total:s.snapshot().courseTime,splits:s.snapshot().splits});
 console.log(JSON.stringify({scope:'synthetic pose setup, real native boundary check, Resume and score persistence',failed,end:{state:s.state,valid:s.snapshot().courseValid,gate:s.course.next},stored,writes:map.size},null,2));s.world.dispose();
}finally{await server.close();}
