import {translate,type Language} from './i18n';
/** Keep source copy per node; never rebuild controls or application state. */
export class LocalizedDOM {
  private sources=new WeakMap<Node,string>();
  private attributes=new WeakMap<Element,Map<string,string>>();
  constructor(public language:Language){}
  text(node:HTMLElement,value:string){this.sources.set(node,value);const translated=translate(value,this.language);if(node.textContent!==translated)node.textContent=translated;}
  apply(root:HTMLElement){
    const walk=(node:Node)=>{
      if(node instanceof HTMLElement){
        if(node.tagName==='OPTION'&&!node.hasAttribute('value'))node.setAttribute('value',node.textContent??'');
        let attrs=this.attributes.get(node);if(!attrs){attrs=new Map();this.attributes.set(node,attrs);for(const name of ['aria-label','title','placeholder'])if(node.hasAttribute(name))attrs.set(name,node.getAttribute(name)!);}
        for(const [name,value] of attrs)node.setAttribute(name,translate(value,this.language));
        const source=this.sources.get(node);if(source!==undefined){const value=translate(source,this.language);if(node.textContent!==value)node.textContent=value;return;}
      }
      if(node.nodeType===Node.TEXT_NODE){let source=this.sources.get(node);if(source===undefined){source=node.textContent??'';this.sources.set(node,source);}const match=source.match(/^(\s*)([\s\S]*?)(\s*)$/)!;node.textContent=match[1]+translate(match[2],this.language)+match[3];return;}
      for(const child of Array.from(node.childNodes))walk(child);
    };walk(root);
  }
}
