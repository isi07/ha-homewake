var j=globalThis,I=j.ShadowRoot&&(j.ShadyCSS===void 0||j.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,X=Symbol(),_e=new WeakMap,R=class{constructor(e,t,n){if(this._$cssResult$=!0,n!==X)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o,t=this.t;if(I&&e===void 0){let n=t!==void 0&&t.length===1;n&&(e=_e.get(t)),e===void 0&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),n&&_e.set(t,e))}return e}toString(){return this.cssText}},$e=i=>new R(typeof i=="string"?i:i+"",void 0,X),ee=(i,...e)=>{let t=i.length===1?i[0]:e.reduce((n,s,r)=>n+(a=>{if(a._$cssResult$===!0)return a.cssText;if(typeof a=="number")return a;throw Error("Value passed to 'css' function must be a 'css' function result: "+a+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(s)+i[r+1],i[0]);return new R(t,i,X)},be=(i,e)=>{if(I)i.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of e){let n=document.createElement("style"),s=j.litNonce;s!==void 0&&n.setAttribute("nonce",s),n.textContent=t.cssText,i.appendChild(n)}},te=I?i=>i:i=>i instanceof CSSStyleSheet?(e=>{let t="";for(let n of e.cssRules)t+=n.cssText;return $e(t)})(i):i;var{is:Ke,defineProperty:Fe,getOwnPropertyDescriptor:Ze,getOwnPropertyNames:Ge,getOwnPropertySymbols:Ye,getPrototypeOf:Je}=Object,B=globalThis,ve=B.trustedTypes,Qe=ve?ve.emptyScript:"",Xe=B.reactiveElementPolyfillSupport,C=(i,e)=>i,ne={toAttribute(i,e){switch(e){case Boolean:i=i?Qe:null;break;case Object:case Array:i=i==null?i:JSON.stringify(i)}return i},fromAttribute(i,e){let t=i;switch(e){case Boolean:t=i!==null;break;case Number:t=i===null?null:Number(i);break;case Object:case Array:try{t=JSON.parse(i)}catch{t=null}}return t}},we=(i,e)=>!Ke(i,e),ye={attribute:!0,type:String,converter:ne,reflect:!1,useDefault:!1,hasChanged:we};Symbol.metadata??=Symbol("metadata"),B.litPropertyMetadata??=new WeakMap;var $=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=ye){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(e,t),!t.noAccessor){let n=Symbol(),s=this.getPropertyDescriptor(e,n,t);s!==void 0&&Fe(this.prototype,e,s)}}static getPropertyDescriptor(e,t,n){let{get:s,set:r}=Ze(this.prototype,e)??{get(){return this[t]},set(a){this[t]=a}};return{get:s,set(a){let l=s?.call(this);r?.call(this,a),this.requestUpdate(e,l,n)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??ye}static _$Ei(){if(this.hasOwnProperty(C("elementProperties")))return;let e=Je(this);e.finalize(),e.l!==void 0&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(C("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(C("properties"))){let t=this.properties,n=[...Ge(t),...Ye(t)];for(let s of n)this.createProperty(s,t[s])}let e=this[Symbol.metadata];if(e!==null){let t=litPropertyMetadata.get(e);if(t!==void 0)for(let[n,s]of t)this.elementProperties.set(n,s)}this._$Eh=new Map;for(let[t,n]of this.elementProperties){let s=this._$Eu(t,n);s!==void 0&&this._$Eh.set(s,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){let t=[];if(Array.isArray(e)){let n=new Set(e.flat(1/0).reverse());for(let s of n)t.unshift(te(s))}else e!==void 0&&t.push(te(e));return t}static _$Eu(e,t){let n=t.attribute;return n===!1?void 0:typeof n=="string"?n:typeof e=="string"?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),this.renderRoot!==void 0&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){let e=new Map,t=this.constructor.elementProperties;for(let n of t.keys())this.hasOwnProperty(n)&&(e.set(n,this[n]),delete this[n]);e.size>0&&(this._$Ep=e)}createRenderRoot(){let e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return be(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,n){this._$AK(e,n)}_$ET(e,t){let n=this.constructor.elementProperties.get(e),s=this.constructor._$Eu(e,n);if(s!==void 0&&n.reflect===!0){let r=(n.converter?.toAttribute!==void 0?n.converter:ne).toAttribute(t,n.type);this._$Em=e,r==null?this.removeAttribute(s):this.setAttribute(s,r),this._$Em=null}}_$AK(e,t){let n=this.constructor,s=n._$Eh.get(e);if(s!==void 0&&this._$Em!==s){let r=n.getPropertyOptions(s),a=typeof r.converter=="function"?{fromAttribute:r.converter}:r.converter?.fromAttribute!==void 0?r.converter:ne;this._$Em=s;let l=a.fromAttribute(t,r.type);this[s]=l??this._$Ej?.get(s)??l,this._$Em=null}}requestUpdate(e,t,n,s=!1,r){if(e!==void 0){let a=this.constructor;if(s===!1&&(r=this[e]),n??=a.getPropertyOptions(e),!((n.hasChanged??we)(r,t)||n.useDefault&&n.reflect&&r===this._$Ej?.get(e)&&!this.hasAttribute(a._$Eu(e,n))))return;this.C(e,t,n)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(e,t,{useDefault:n,reflect:s,wrapped:r},a){n&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,a??t??this[e]),r!==!0||a!==void 0)||(this._$AL.has(e)||(this.hasUpdated||n||(t=void 0),this._$AL.set(e,t)),s===!0&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let e=this.scheduleUpdate();return e!=null&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[s,r]of this._$Ep)this[s]=r;this._$Ep=void 0}let n=this.constructor.elementProperties;if(n.size>0)for(let[s,r]of n){let{wrapped:a}=r,l=this[s];a!==!0||this._$AL.has(s)||l===void 0||this.C(s,void 0,r,l)}}let e=!1,t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(n=>n.hostUpdate?.()),this.update(t)):this._$EM()}catch(n){throw e=!1,this._$EM(),n}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(e){}firstUpdated(e){}};$.elementStyles=[],$.shadowRootOptions={mode:"open"},$[C("elementProperties")]=new Map,$[C("finalized")]=new Map,Xe?.({ReactiveElement:$}),(B.reactiveElementVersions??=[]).push("2.1.2");var se=globalThis,Ae=i=>i,W=se.trustedTypes,xe=W?W.createPolicy("lit-html",{createHTML:i=>i}):void 0,re="$lit$",b=`lit$${Math.random().toFixed(9).slice(2)}$`,ae="?"+b,et=`<${ae}>`,A=document,H=()=>A.createComment(""),O=i=>i===null||typeof i!="object"&&typeof i!="function",oe=Array.isArray,Ce=i=>oe(i)||typeof i?.[Symbol.iterator]=="function",ie=`[ 	
\f\r]`,P=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,ke=/-->/g,Ee=/>/g,y=RegExp(`>|${ie}(?:([^\\s"'>=/]+)(${ie}*=${ie}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),Se=/'/g,Te=/"/g,Pe=/^(?:script|style|textarea|title)$/i,le=i=>(e,...t)=>({_$litType$:i,strings:e,values:t}),d=le(1),mt=le(2),_t=le(3),g=Symbol.for("lit-noChange"),h=Symbol.for("lit-nothing"),Re=new WeakMap,w=A.createTreeWalker(A,129);function He(i,e){if(!oe(i)||!i.hasOwnProperty("raw"))throw Error("invalid template strings array");return xe!==void 0?xe.createHTML(e):e}var Oe=(i,e)=>{let t=i.length-1,n=[],s,r=e===2?"<svg>":e===3?"<math>":"",a=P;for(let l=0;l<t;l++){let o=i[l],c,f,u=-1,p=0;for(;p<o.length&&(a.lastIndex=p,f=a.exec(o),f!==null);)p=a.lastIndex,a===P?f[1]==="!--"?a=ke:f[1]!==void 0?a=Ee:f[2]!==void 0?(Pe.test(f[2])&&(s=RegExp("</"+f[2],"g")),a=y):f[3]!==void 0&&(a=y):a===y?f[0]===">"?(a=s??P,u=-1):f[1]===void 0?u=-2:(u=a.lastIndex-f[2].length,c=f[1],a=f[3]===void 0?y:f[3]==='"'?Te:Se):a===Te||a===Se?a=y:a===ke||a===Ee?a=P:(a=y,s=void 0);let m=a===y&&i[l+1].startsWith("/>")?" ":"";r+=a===P?o+et:u>=0?(n.push(c),o.slice(0,u)+re+o.slice(u)+b+m):o+b+(u===-2?l:m)}return[He(i,r+(i[t]||"<?>")+(e===2?"</svg>":e===3?"</math>":"")),n]},z=class i{constructor({strings:e,_$litType$:t},n){let s;this.parts=[];let r=0,a=0,l=e.length-1,o=this.parts,[c,f]=Oe(e,t);if(this.el=i.createElement(c,n),w.currentNode=this.el.content,t===2||t===3){let u=this.el.content.firstChild;u.replaceWith(...u.childNodes)}for(;(s=w.nextNode())!==null&&o.length<l;){if(s.nodeType===1){if(s.hasAttributes())for(let u of s.getAttributeNames())if(u.endsWith(re)){let p=f[a++],m=s.getAttribute(u).split(b),D=/([.?@])?(.*)/.exec(p);o.push({type:1,index:r,name:D[2],strings:m,ctor:D[1]==="."?q:D[1]==="?"?K:D[1]==="@"?F:k}),s.removeAttribute(u)}else u.startsWith(b)&&(o.push({type:6,index:r}),s.removeAttribute(u));if(Pe.test(s.tagName)){let u=s.textContent.split(b),p=u.length-1;if(p>0){s.textContent=W?W.emptyScript:"";for(let m=0;m<p;m++)s.append(u[m],H()),w.nextNode(),o.push({type:2,index:++r});s.append(u[p],H())}}}else if(s.nodeType===8)if(s.data===ae)o.push({type:2,index:r});else{let u=-1;for(;(u=s.data.indexOf(b,u+1))!==-1;)o.push({type:7,index:r}),u+=b.length-1}r++}}static createElement(e,t){let n=A.createElement("template");return n.innerHTML=e,n}};function x(i,e,t=i,n){if(e===g)return e;let s=n!==void 0?t._$Co?.[n]:t._$Cl,r=O(e)?void 0:e._$litDirective$;return s?.constructor!==r&&(s?._$AO?.(!1),r===void 0?s=void 0:(s=new r(i),s._$AT(i,t,n)),n!==void 0?(t._$Co??=[])[n]=s:t._$Cl=s),s!==void 0&&(e=x(i,s._$AS(i,e.values),s,n)),e}var V=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){let{el:{content:t},parts:n}=this._$AD,s=(e?.creationScope??A).importNode(t,!0);w.currentNode=s;let r=w.nextNode(),a=0,l=0,o=n[0];for(;o!==void 0;){if(a===o.index){let c;o.type===2?c=new S(r,r.nextSibling,this,e):o.type===1?c=new o.ctor(r,o.name,o.strings,this,e):o.type===6&&(c=new Z(r,this,e)),this._$AV.push(c),o=n[++l]}a!==o?.index&&(r=w.nextNode(),a++)}return w.currentNode=A,s}p(e){let t=0;for(let n of this._$AV)n!==void 0&&(n.strings!==void 0?(n._$AI(e,n,t),t+=n.strings.length-2):n._$AI(e[t])),t++}},S=class i{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,n,s){this.type=2,this._$AH=h,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=n,this.options=s,this._$Cv=s?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,t=this._$AM;return t!==void 0&&e?.nodeType===11&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=x(this,e,t),O(e)?e===h||e==null||e===""?(this._$AH!==h&&this._$AR(),this._$AH=h):e!==this._$AH&&e!==g&&this._(e):e._$litType$!==void 0?this.$(e):e.nodeType!==void 0?this.T(e):Ce(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==h&&O(this._$AH)?this._$AA.nextSibling.data=e:this.T(A.createTextNode(e)),this._$AH=e}$(e){let{values:t,_$litType$:n}=e,s=typeof n=="number"?this._$AC(e):(n.el===void 0&&(n.el=z.createElement(He(n.h,n.h[0]),this.options)),n);if(this._$AH?._$AD===s)this._$AH.p(t);else{let r=new V(s,this),a=r.u(this.options);r.p(t),this.T(a),this._$AH=r}}_$AC(e){let t=Re.get(e.strings);return t===void 0&&Re.set(e.strings,t=new z(e)),t}k(e){oe(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,n,s=0;for(let r of e)s===t.length?t.push(n=new i(this.O(H()),this.O(H()),this,this.options)):n=t[s],n._$AI(r),s++;s<t.length&&(this._$AR(n&&n._$AB.nextSibling,s),t.length=s)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);e!==this._$AB;){let n=Ae(e).nextSibling;Ae(e).remove(),e=n}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},k=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,n,s,r){this.type=1,this._$AH=h,this._$AN=void 0,this.element=e,this.name=t,this._$AM=s,this.options=r,n.length>2||n[0]!==""||n[1]!==""?(this._$AH=Array(n.length-1).fill(new String),this.strings=n):this._$AH=h}_$AI(e,t=this,n,s){let r=this.strings,a=!1;if(r===void 0)e=x(this,e,t,0),a=!O(e)||e!==this._$AH&&e!==g,a&&(this._$AH=e);else{let l=e,o,c;for(e=r[0],o=0;o<r.length-1;o++)c=x(this,l[n+o],t,o),c===g&&(c=this._$AH[o]),a||=!O(c)||c!==this._$AH[o],c===h?e=h:e!==h&&(e+=(c??"")+r[o+1]),this._$AH[o]=c}a&&!s&&this.j(e)}j(e){e===h?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}},q=class extends k{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===h?void 0:e}},K=class extends k{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==h)}},F=class extends k{constructor(e,t,n,s,r){super(e,t,n,s,r),this.type=5}_$AI(e,t=this){if((e=x(this,e,t,0)??h)===g)return;let n=this._$AH,s=e===h&&n!==h||e.capture!==n.capture||e.once!==n.once||e.passive!==n.passive,r=e!==h&&(n===h||s);s&&this.element.removeEventListener(this.name,this,n),r&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}},Z=class{constructor(e,t,n){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=n}get _$AU(){return this._$AM._$AU}_$AI(e){x(this,e)}},ze={M:re,P:b,A:ae,C:1,L:Oe,R:V,D:Ce,V:x,I:S,H:k,N:K,U:F,B:q,F:Z},tt=se.litHtmlPolyfillSupport;tt?.(z,S),(se.litHtmlVersions??=[]).push("3.3.3");var Ue=(i,e,t)=>{let n=t?.renderBefore??e,s=n._$litPart$;if(s===void 0){let r=t?.renderBefore??null;n._$litPart$=s=new S(e.insertBefore(H(),r),r,void 0,t??{})}return s._$AI(i),s};var ce=globalThis,v=class extends ${constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=Ue(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return g}};v._$litElement$=!0,v.finalized=!0,ce.litElementHydrateSupport?.({LitElement:v});var nt=ce.litElementPolyfillSupport;nt?.({LitElement:v});(ce.litElementVersions??=[]).push("4.2.2");var E={ATTRIBUTE:1,CHILD:2,PROPERTY:3,BOOLEAN_ATTRIBUTE:4,EVENT:5,ELEMENT:6},Me=i=>(...e)=>({_$litDirective$:i,values:e}),G=class{constructor(e){}get _$AU(){return this._$AM._$AU}_$AT(e,t,n){this._$Ct=e,this._$AM=t,this._$Ci=n}_$AS(e,t){return this.update(e,t)}update(e,t){return this.render(...t)}};var{I:Ht}=ze;var Le=i=>i.strings===void 0;var it={},Ne=(i,e=it)=>i._$AH=e;var ue=Me(class extends G{constructor(i){if(super(i),i.type!==E.PROPERTY&&i.type!==E.ATTRIBUTE&&i.type!==E.BOOLEAN_ATTRIBUTE)throw Error("The `live` directive is not allowed on child or event bindings");if(!Le(i))throw Error("`live` bindings can only contain a single expression")}render(i){return i}update(i,[e]){if(e===g||e===h)return e;let t=i.element,n=i.name;if(i.type===E.PROPERTY){if(e===t[n])return g}else if(i.type===E.BOOLEAN_ATTRIBUTE){if(!!e===t.hasAttribute(n))return g}else if(i.type===E.ATTRIBUTE&&t.getAttribute(n)===e+"")return g;return Ne(i),e}});var L="homewake",N=new Set(["unknown","unavailable"]),st={Person:"person",Raum:"raum"};function De(i){let e=new Map;for(let n of Object.values(i.entities)){if(!n||n.platform!==L||!n.device_id||!n.translation_key)continue;let s=e.get(n.device_id)??{};s[n.translation_key]=n.entity_id,e.set(n.device_id,s)}let t=[];for(let[n,s]of e){let r=i.devices[n],a=st[r?.model??""],l=r?.identifiers?.find(([c])=>c===L)?.[1];if(!r||!a||!l)continue;let o=r.name_by_user||r.name||l;t.push({id:l,geraetId:n,typ:a,name:o,entities:s})}return t.sort((n,s)=>(n.typ===s.typ?0:n.typ==="person"?-1:1)||n.name.localeCompare(s.name,i.locale.language))}function _(i,e,t){let n=e.entities[t];return n&&i.states[n]||null}function Y(i,e,t){let n=_(i,e,t);return!n||N.has(n.state)?null:n.state==="on"}function fe(i){if(typeof i!="string"||N.has(i))return null;let e=new Date(i);return Number.isNaN(e.getTime())?null:e}function U(i,e,t){return fe(_(i,e,t)?.state)}function je(i,e){return!e||N.has(e.state)?null:i.formatEntityState?.(e)??e.state}function de(i,e,t){let n=e?.attributes[t];return!e||n===void 0||n===null?null:i.formatEntityAttributeValue?.(e,t)??String(n)}function M(i,e,t,n=null){return e?[{art:i,zeit:e,vergangen:e.getTime()<=t.getTime(),naechster:n!==null&&e.getTime()===n.getTime()}]:[]}function T(i,e,t){let n=_(i,e,t);return n!==null&&n.state!=="unavailable"}function he(i,e,t){return{entity:e.entities[t]??null,an:Y(i,e,t),bedienbar:T(i,e,t)}}function rt(i,e,t){let n=_(i,e,t);return{entity:e.entities[t]??null,wert:n&&!N.has(n.state)?n.state.slice(0,5):null,bedienbar:T(i,e,t)}}function pe(i,e,t){let n=_(i,e,t),s=n&&!N.has(n.state)?n.state:null,r=n?.attributes.options,a=Array.isArray(r)?r.filter(o=>typeof o=="string"):[];s!==null&&!a.includes(s)&&a.push(s);let l=o=>(n&&i.formatEntityState?.(n,o))??o;return{entity:e.entities[t]??null,wert:s,text:je(i,n),optionen:a.map(o=>({wert:o,text:l(o)})),bedienbar:T(i,e,t)}}function Ie(i,e,t,n){let s=_(i,e,"status"),r=p=>fe(s?.attributes[p]),a=U(i,e,"naechster_wecker"),l=p=>{let m=r(`tagesbeginn_${p}`);return{datum:m,status:de(i,s,`status_${p}`),grund:de(i,s,`grund_${p}`),ereignisse:[...M("wecker",m,n,a),...M("ende",r(`tagesende_${p}`),n)]}},o=_(i,e,"raum"),c=je(i,o),f=o?.attributes.raum_id,u=t.find(p=>p.typ==="raum"&&p.id===f);return{typ:"person",name:e.name,verfuegbar:T(i,e,"status"),wach:Y(i,e,"wach"),raum:c===null?null:{name:c,id:u?u.id:null},raumAuswahl:pe(i,e,"raum"),tage:[l("heute"),l("morgen")],ausnahme:{schalter:he(i,e,"ausnahme"),zeit:rt(i,e,"ausnahme_zeit")},profile:["zeitplan","standard","ausnahme"].map(p=>({profil:p,licht:he(i,e,`licht_${p}`),radio:he(i,e,`radio_${p}`)})),favorit:pe(i,e,"favorit")}}function Be(i,e,t,n){let s=[U(i,e,"weckzeit"),U(i,e,"weckzeit_morgen")],r=s.find(c=>c!==null&&c.getTime()>n.getTime())??null,a=(c,f)=>{let u=U(i,e,`tagesbeginn${c}`);return{datum:f??u,status:null,grund:null,ereignisse:[...M("wecker",f,n,r),...M("beginn",u,n),...M("ende",U(i,e,`tagesende${c}`),n)]}},l=_(i,e,"weckzeit"),o=t.filter(c=>c.typ==="person"&&_(i,c,"raum")?.attributes.raum_id===e.id).map(c=>({name:c.name,id:c.id}));return{typ:"raum",name:e.name,verfuegbar:T(i,e,"weckzeit"),wach:Y(i,e,"wach"),tag:Y(i,e,"tag"),quelle:de(i,l,"quelle"),personen:o,favorit:e.entities.standard_favorit?pe(i,e,"standard_favorit"):null,tage:[a("",s[0]??null),a("_morgen",s[1]??null)]}}function We(i,e){let t=[];for(let n of e){if(n.typ!=="raum")continue;let s=fe(_(i,n,"wach")?.attributes.wecken_bis);if(s){let r=n.entities.wecken_beenden,a=r?{entity:r,bedienbar:T(i,n,"wecken_beenden")}:null;t.push({raum:{name:n.name,id:n.id},bis:s,taste:a})}}return t.sort((n,s)=>n.bis.getTime()-s.bis.getTime())}var at={wach:"wach",schlaeft:"schl\xE4ft",tag:"Tag",nacht:"Nacht",heute:"Heute",morgen:"Morgen",wecker:"Wecker",beginn:"Tagesbeginn",ende:"Tagesende",raum:"Raum",ausnahme:"Ausnahme",an:"an",aus:"aus",licht:"Licht",radio:"Radio",zeitplan:"Zeitplan",standard:"Frei",favorit:"Radio-Favorit",standard_favorit:"Standard-Favorit",quelle:"Quelle",personen:"Personen",niemand:"niemand",weckt_bis:"weckt bis",einstellungen:"Einstellungen in Home Assistant",auswahl:"Person oder Raum",leer:"Keine Personen oder R\xE4ume von HomeWake gefunden.",nicht_verfuegbar:"nicht verf\xFCgbar",wecken_beenden:"Wecken beenden",zum_raum:"Zum Raum",ausnahme_zeit:"Uhrzeit der Ausnahme",fehler:"Aktion fehlgeschlagen",schliessen:"Schlie\xDFen",editor_objekt:"Zuerst zeigen",editor_objekt_hilfe:"Person oder Raum, den die Karte beim Laden zeigt; leer = die erste Person"},Ve={wach:"awake",schlaeft:"asleep",tag:"Day",nacht:"Night",heute:"Today",morgen:"Tomorrow",wecker:"Alarm",beginn:"Start of day",ende:"End of day",raum:"Room",ausnahme:"Exception",an:"on",aus:"off",licht:"Light",radio:"Radio",zeitplan:"Schedule",standard:"Day off",favorit:"Radio favorite",standard_favorit:"Default favorite",quelle:"Source",personen:"Persons",niemand:"nobody",weckt_bis:"waking until",einstellungen:"Settings in Home Assistant",auswahl:"Person or room",leer:"No HomeWake persons or rooms found.",nicht_verfuegbar:"unavailable",wecken_beenden:"Stop alarm",zum_raum:"Go to room",ausnahme_zeit:"Exception time",fehler:"Action failed",schliessen:"Close",editor_objekt:"Show first",editor_objekt_hilfe:"Person or room shown when the card loads; empty = the first person"},ot={de:at,en:Ve};function J(i){return ot[i.split("-")[0]??""]??Ve}function ge(i,e,t){return new Intl.DateTimeFormat(e,{hour:"2-digit",minute:"2-digit",hourCycle:"h23",timeZone:t}).format(i)}function qe(i,e,t){return new Intl.DateTimeFormat(e,{weekday:"long",day:"2-digit",month:"2-digit",timeZone:t}).format(i)}var lt="/config/integrations/integration/homewake",ct=6e4;function ut(i){history.pushState(null,"",i),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}}))}function ht(i){if(typeof i=="string")return i;let e=i?.message;return typeof e=="string"?e:""}var me=class extends v{constructor(){super();this._gezeigt=null;this._auswahl=null,this._fehler=null,this._laeuft=new Set}static{this.properties={hass:{attribute:!1},_config:{state:!0},_auswahl:{state:!0},_fehler:{state:!0},_laeuft:{state:!0}}}static getStubConfig(){return{}}static getConfigForm(){let t=()=>J(document.documentElement.lang||"en");return{schema:[{name:"objekt",selector:{device:{filter:[{integration:L,model:"Person"},{integration:L,model:"Raum"}]}}}],computeLabel:n=>n.name==="objekt"?t().editor_objekt:n.name,computeHelper:n=>n.name==="objekt"?t().editor_objekt_hilfe:""}}setConfig(t){this._config=t,this._auswahl=null}getCardSize(){return 6}connectedCallback(){super.connectedCallback(),this._takt=setInterval(()=>this.requestUpdate(),ct)}disconnectedCallback(){super.disconnectedCallback(),clearInterval(this._takt),this._takt=void 0}_aktiv(t){let n=this._auswahl??this._config?.objekt;return t.find(s=>s.id===n||s.geraetId===n||s.name===n)??t[0]}_waehle(t){t!==null&&(this._auswahl=t)}async _aktion(t,n,s,r={}){if(!this._laeuft.has(s)){this._laeuft=new Set([...this._laeuft,s]);try{if(!this.hass?.callService)throw"";await this.hass.callService(t,n,r,{entity_id:s},!1),this._fehler=null}catch(a){this._fehler=ht(a)}finally{let a=new Set(this._laeuft);a.delete(s),this._laeuft=a}}}_gesperrt(t){return!t.bedienbar||t.entity===null}_beschaeftigt(t){return t!==null&&this._laeuft.has(t)?"true":"false"}_umschalten(t){t.entity&&this._aktion("switch",t.an?"turn_off":"turn_on",t.entity)}render(){let t=this.hass;if(!t)return h;let n=J(t.locale.language),s=De(t),r=this._aktiv(s);if(this._gezeigt=r?.id??null,!r)return d`<ha-card><div class="leer">${n.leer}</div></ha-card>`;let a=new Date,l=r.typ==="person"?Ie(t,r,s,a):Be(t,r,s,a);return d`<ha-card>
      ${this._laufend(We(t,s),t,n)} ${this._fehlerZeile(n)}
      <div class="kopf">
        <select
          class="name"
          aria-label=${n.auswahl}
          @change=${o=>this._waehle(o.target.value)}
        >
          ${s.map(o=>d`<option value=${o.id}>${o.name}</option>`)}
        </select>
        <span class="pille ${l.wach?"an":""}"
          >${l.wach===null?"\u2013":l.wach?n.wach:n.schlaeft}</span
        >
        <button
          class="zahnrad"
          title=${n.einstellungen}
          aria-label=${n.einstellungen}
          @click=${()=>ut(lt)}
        >
          <ha-icon icon="mdi:cog"></ha-icon>
        </button>
      </div>
      ${l.verfuegbar?h:d`<div class="hinweis">${n.nicht_verfuegbar}</div>`}
      <div class="tage">
        ${this._tag(l.tage[0],n.heute,t)} ${this._tag(l.tage[1],n.morgen,t)}
      </div>
      ${l.typ==="person"?this._person(l,n):this._raum(l,n)}
    </ha-card>`}updated(){let t=this.renderRoot.querySelector("select.name");t&&this._gezeigt!==null&&(t.value=this._gezeigt)}_laufend(t,n,s){if(t.length===0)return h;let r=a=>ge(a,n.locale.language,n.config.time_zone);return d`<div class="laufend">
      ${t.map(a=>d`<div class="zeile">
          <ha-icon icon="mdi:alarm"></ha-icon>
          <button class="raumname" @click=${()=>this._waehle(a.raum.id)}>
            ${a.raum.name}
          </button>
          <span class="bis">${s.weckt_bis} ${r(a.bis)}</span>
          ${this._beenden(a.taste,s)}
        </div>`)}
    </div>`}_beenden(t,n){return t===null?h:d`<button
      class="beenden"
      ?disabled=${!t.bedienbar}
      aria-busy=${this._beschaeftigt(t.entity)}
      @click=${()=>this._aktion("button","press",t.entity)}
    >
      <ha-icon icon="mdi:alarm-off"></ha-icon>${n.wecken_beenden}
    </button>`}_fehlerZeile(t){return this._fehler===null?h:d`<div class="fehler" role="alert">
      <ha-icon icon="mdi:alert-circle"></ha-icon>
      <span>${t.fehler}${this._fehler?`: ${this._fehler}`:""}</span>
      <button
        title=${t.schliessen}
        aria-label=${t.schliessen}
        @click=${()=>{this._fehler=null}}
      >
        ✕
      </button>
    </div>`}_tag(t,n,s){let r=J(s.locale.language),a=s.locale.language,l=s.config.time_zone;return d`<div class="tag">
      <div class="tagkopf">
        <span class="wann">${n}</span>
        <span class="datum">${t.datum?qe(t.datum,a,l):""}</span>
        ${t.status?d`<span class="status">${t.status}${t.grund?` \xB7 ${t.grund}`:""}</span>`:h}
      </div>
      ${t.ereignisse.map(o=>d`<div
          class="ereignis ${o.vergangen?"vergangen":""} ${o.naechster?"naechster":""}"
        >
          <span>${r[o.art]}</span><span>${ge(o.zeit,a,l)}</span>
        </div>`)}
    </div>`}_verweis(t,n){return n===null?d`<span>${t}</span>`:d`<button class="verweis" @click=${()=>this._waehle(n)}>${t}</button>`}_knopf(t,n,s,r){let a=t.an===null?"unbekannt":t.an?"an":"aus",l=t.an===null?"\u2013":t.an?r.an:r.aus;return d`<button
      class="knopf ${a}"
      title="${n}: ${l}"
      aria-label="${n} ${s}"
      aria-pressed=${t.an===null?"mixed":t.an?"true":"false"}
      aria-busy=${this._beschaeftigt(t.entity)}
      ?disabled=${this._gesperrt(t)}
      @click=${()=>this._umschalten(t)}
    >
      ${n}
    </button>`}_schalter(t,n,s){let r=t.an===null?"\u2013":t.an?s.an:s.aus;return d`<button
      class="schalter ${t.an?"an":""}"
      role="switch"
      aria-checked=${t.an?"true":"false"}
      aria-label=${n}
      title="${n}: ${r}"
      aria-busy=${this._beschaeftigt(t.entity)}
      ?disabled=${this._gesperrt(t)}
      @click=${()=>this._umschalten(t)}
    >
      <span class="griff"></span>
    </button>`}_uhrzeit(t,n){let s=a=>{a.value=t.wert??""},r=async a=>{let l=a.target,o=l.value;if(!o||o===t.wert||t.entity===null){s(l);return}await this._aktion("time","set_value",t.entity,{time:`${o}:00`}),this._fehler!==null&&s(l)};return d`<input
      type="time"
      aria-label=${n}
      .value=${t.wert??""}
      aria-busy=${this._beschaeftigt(t.entity)}
      ?disabled=${this._gesperrt(t)}
      @blur=${r}
      @keydown=${a=>{a.key==="Enter"&&a.target.blur()}}
    />`}_liste(t,n){let s=r=>{let a=r.target.value;a===t.wert||t.entity===null||this._aktion("select","select_option",t.entity,{option:a})};return d`<select
      class="liste"
      aria-label=${n}
      aria-busy=${this._beschaeftigt(t.entity)}
      ?disabled=${this._gesperrt(t)}
      @change=${s}
    >
      ${t.wert===null?d`<option value="" disabled .selected=${ue(!0)}>–</option>`:h}
      ${t.optionen.map(r=>d`<option value=${r.wert} .selected=${ue(r.wert===t.wert)}>${r.text}</option>`)}
    </select>`}_person(t,n){let s=t.raum?.id?t.raum:null;return d`<div class="werte">
      <div class="raum">
        <span class="label">${n.raum}</span>
        ${this._liste(t.raumAuswahl,n.raum)}
        ${s?d`<button
              class="verweis"
              title="${n.zum_raum} ${s.name}"
              aria-label="${n.zum_raum} ${s.name}"
              @click=${()=>this._waehle(s.id)}
            >
              <ha-icon icon="mdi:arrow-right"></ha-icon>
            </button>`:h}
      </div>
      <div class="ausnahme">
        <span class="label">${n.ausnahme}</span>
        ${this._schalter(t.ausnahme.schalter,n.ausnahme,n)}
        ${this._uhrzeit(t.ausnahme.zeit,n.ausnahme_zeit)}
      </div>
      ${t.profile.map(r=>d`<div class="profil">
          <span class="label">${n[r.profil]}</span>
          ${this._knopf(r.licht,n.licht,n[r.profil],n)}
          ${this._knopf(r.radio,n.radio,n[r.profil],n)}
        </div>`)}
      <div class="favorit">
        <span class="label">${n.favorit}</span>${this._liste(t.favorit,n.favorit)}
      </div>
    </div>`}_raum(t,n){return d`<div class="werte">
      <div>
        <span class="label">${n.tag}/${n.nacht}</span>
        <span>${t.tag===null?"\u2013":t.tag?n.tag:n.nacht}</span>
      </div>
      <div><span class="label">${n.quelle}</span><span>${t.quelle??"\u2013"}</span></div>
      <div class="personen">
        <span class="label">${n.personen}</span>
        ${t.personen.length===0?d`<span>${n.niemand}</span>`:t.personen.map(s=>this._verweis(s.name,s.id))}
      </div>
      ${t.favorit===null?h:d`<div class="favorit">
            <span class="label">${n.standard_favorit}</span>
            ${this._liste(t.favorit,n.standard_favorit)}
          </div>`}
    </div>`}static{this.styles=ee`
    :host {
      display: block;
    }
    ha-card {
      /* Maßgeblich ist die Breite der Karte, nicht des Bildschirms (E62) */
      container-type: inline-size;
      padding: 10px 12px 12px;
    }
    button {
      font: inherit;
      color: inherit;
      background: none;
      border: none;
      padding: 0;
      cursor: pointer;
    }
    button:disabled {
      cursor: default;
    }
    .leer,
    .hinweis {
      color: var(--secondary-text-color);
    }
    /* Laufende Wecker: Balken mit Knopf „Wecken beenden“ (B3) */
    .laufend {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-bottom: 8px;
    }
    .laufend .zeile {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 4px 8px;
      padding: 6px 6px 6px 10px;
      border-radius: 8px;
      background: var(--warning-color, #ffa600);
      color: var(--text-primary-color, #fff);
    }
    .laufend .raumname {
      font-weight: 600;
      text-decoration: underline;
    }
    .laufend .bis {
      flex: 1;
      white-space: nowrap;
    }
    .laufend .beenden {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      min-height: 36px;
      padding: 0 12px;
      border-radius: 18px;
      background: var(--card-background-color, #fff);
      color: var(--warning-color, #ffa600);
      font-weight: 700;
      margin-left: auto;
    }
    .laufend .beenden:disabled {
      opacity: 0.6;
    }
    .fehler {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      margin-bottom: 8px;
      border-radius: 8px;
      background: var(--error-color, #db4437);
      color: var(--text-primary-color, #fff);
    }
    .fehler span {
      flex: 1;
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .fehler button {
      min-width: 32px;
      min-height: 32px;
    }
    .kopf {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .kopf .name {
      flex: 1;
      min-width: 0;
      font: inherit;
      font-size: 1.2em;
      font-weight: 500;
      color: var(--primary-text-color);
      background: none;
      border: none;
      padding: 4px 0;
    }
    .pille {
      padding: 2px 10px;
      border-radius: 999px;
      font-size: 0.85em;
      background: var(--secondary-background-color, #e0e0e0);
      color: var(--secondary-text-color);
    }
    .pille.an {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .zahnrad {
      color: var(--secondary-text-color);
      min-width: 32px;
      min-height: 32px;
    }
    .tage {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin: 8px 0 10px;
    }
    @container (max-width: 280px) {
      .tage {
        grid-template-columns: 1fr;
      }
      /* Beschriftung über dem Element, damit Liste und Pfeil in eine Zeile passen */
      .werte .label {
        flex-basis: 100%;
      }
      .werte .liste {
        flex: 1 1 0;
      }
    }
    .tag {
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      padding: 6px 8px;
      font-size: 0.9em;
      min-width: 0;
    }
    .tagkopf {
      display: flex;
      flex-wrap: wrap;
      gap: 0 6px;
      margin-bottom: 4px;
    }
    .wann {
      font-weight: 600;
    }
    .datum,
    .status {
      color: var(--secondary-text-color);
    }
    .status {
      flex-basis: 100%;
    }
    .ereignis {
      display: flex;
      justify-content: space-between;
      gap: 4px;
    }
    .ereignis span:first-child {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .ereignis.vergangen {
      opacity: 0.45;
    }
    .ereignis.naechster {
      font-weight: 700;
    }
    .werte > div {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 4px 8px;
      padding: 2px 0;
      min-height: 36px;
    }
    .label {
      min-width: 8em;
      color: var(--secondary-text-color);
    }
    /* Bedienelemente in HA-Farben (E74) */
    .liste,
    input[type="time"] {
      font: inherit;
      color: var(--primary-text-color);
      background: var(--secondary-background-color, #f0f0f0);
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      min-height: 32px;
      padding: 0 6px;
      box-sizing: border-box;
    }
    .liste {
      flex: 1 1 8em;
      min-width: 0;
      max-width: 100%;
    }
    .liste:disabled,
    input[type="time"]:disabled,
    .knopf:disabled,
    .schalter:disabled {
      opacity: 0.4;
    }
    .knopf {
      min-height: 32px;
      min-width: 4.5em;
      padding: 0 10px;
      border-radius: 16px;
      border: 1px solid var(--divider-color);
    }
    .knopf.an {
      background: var(--primary-color);
      border-color: var(--primary-color);
      color: var(--text-primary-color, #fff);
      font-weight: 500;
    }
    .knopf.aus {
      color: var(--secondary-text-color);
      text-decoration: line-through;
    }
    .knopf.unbekannt {
      color: var(--secondary-text-color);
      font-style: italic;
    }
    .schalter {
      position: relative;
      width: 44px;
      height: 24px;
      border-radius: 12px;
      background: var(--switch-unchecked-track-color, #9e9e9e);
      flex: none;
    }
    .schalter .griff {
      position: absolute;
      top: 3px;
      left: 3px;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: #fff;
      transition: left 0.15s;
    }
    .schalter.an {
      background: var(--primary-color);
    }
    .schalter.an .griff {
      left: 23px;
    }
    .verweis {
      color: var(--primary-color);
      text-decoration: underline;
    }
    .raum .verweis {
      min-width: 32px;
      min-height: 32px;
      text-decoration: none;
    }
  `}};customElements.get("homewake-card")||customElements.define("homewake-card",me);var Q=window;Q.customCards=Q.customCards??[];Q.customCards.some(i=>i.type==="homewake-card")||Q.customCards.push({type:"homewake-card",name:"HomeWake",description:"Weckzeiten einer Person oder eines Raums, heute und morgen, mit Bedienung",preview:!1});export{me as HomeWakeCard};
