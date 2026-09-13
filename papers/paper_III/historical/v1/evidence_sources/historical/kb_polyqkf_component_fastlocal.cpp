#include <algorithm>
#include <chrono>
#include <cstdint>
#include <deque>
#include <iostream>
#include <map>
#include <memory>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
using std::vector; using std::pair; using std::string;
struct DSU{vector<int>p,sz;explicit DSU(int n=0):p(n),sz(n,1){std::iota(p.begin(),p.end(),0);}int add(){int i=p.size();p.push_back(i);sz.push_back(1);return i;}int f(int x){int r=x;while(p[r]!=r)r=p[r];while(p[x]!=x){int q=p[x];p[x]=r;x=q;}return r;}bool u(int a,int b){a=f(a);b=f(b);if(a==b)return false;if(sz[a]<sz[b])std::swap(a,b);p[b]=a;sz[a]+=sz[b];return true;}};
struct Obs{int a,b,y;};
struct KBAlg{
 int w,n; vector<uint32_t> z,o; vector<int> pow3;
 explicit KBAlg(int ww):w(ww){n=1;for(int i=0;i<w;i++)n*=3;pow3.resize(w);int p=1;for(int i=w-1;i>=0;i--){pow3[i]=p;p*=3;}z.resize(n);o.resize(n);for(int idx=0;idx<n;idx++){uint32_t zz=0,oo=0;for(int i=0;i<w;i++){int d=(idx/pow3[i])%3;if(d==1)zz|=1u<<i;else if(d==2)oo|=1u<<i;}z[idx]=zz;o[idx]=oo;}}
 int index(uint32_t zz,uint32_t oo)const{int r=0;for(int i=0;i<w;i++){int d=(zz>>i&1)?1:((oo>>i&1)?2:0);r+=d*pow3[i];}return r;}
 int join(int a,int b)const{return index(z[a]&z[b],o[a]&o[b]);}
};
struct CarrierTheta{const KBAlg&A;DSU d;explicit CarrierTheta(const KBAlg&a):A(a),d(a.n){}int f(int x){return d.f(x);}bool add(int a,int b){std::deque<pair<int,int>>q;q.push_back({a,b});bool ch=false;while(!q.empty()){auto[x,y]=q.front();q.pop_front();x=f(x);y=f(y);if(x==y)continue;int ox=x,oy=y;vector<pair<int,int>>ctx;ctx.reserve(A.n);for(int c=0;c<A.n;c++){int cc=f(c);ctx.push_back({A.join(ox,cc),A.join(oy,cc)});}d.u(x,y);ch=true;for(auto[r,s]:ctx){r=f(r);s=f(s);if(r!=s)q.push_back({r,s});}}return ch;}vector<vector<int>>blocks(){std::map<int,vector<int>>m;for(int a=0;a<A.n;a++)m[f(a)].push_back(a);vector<vector<int>>r;for(auto&kv:m)r.push_back(kv.second);return r;}};
struct QAlg{const KBAlg&A;CarrierTheta&th;int q;vector<int>orig,idxRoot;QAlg(const KBAlg&a,CarrierTheta&t):A(a),th(t){idxRoot.assign(A.n,-1);for(int x=0;x<A.n;x++)if(th.f(x)==x){idxRoot[x]=orig.size();orig.push_back(x);}q=orig.size();}int join(int a,int b)const{int r=th.f(A.join(orig[a],orig[b]));return idxRoot[r];}};
struct H{size_t operator()(uint64_t x)const noexcept{return (size_t)(x^(x>>33));}};static inline uint64_t pc(int a,int b){return (uint64_t)(uint32_t)a<<32|(uint32_t)b;}static inline int pa(uint64_t z){return (int)(z>>32);}static inline int pb(uint64_t z){return (int)(uint32_t)z;}
static inline int rowc(int b){return 1+b;}static inline int colc(int q,int a){return 1+q+a;}static inline bool isrow(int q,int c){return c>=1&&c<1+q;}static inline bool iscol(int q,int c){return c>=1+q&&c<1+2*q;}static inline int ctx(int q,int c){return isrow(q,c)?c-1:(iscol(q,c)?c-(1+q):-1);} 
struct CompatRec{uint64_t k;uint32_t c,v;bool operator<(const CompatRec&o)const{return k<o.k;}};
struct RunRes{vector<pair<int,int>>cp;std::unordered_map<uint64_t,int,H>known;uint64_t endpoints=0,compat_records=0,compat_groups=0,compat_unions=0,implicit_checks=0,implicit_unions=0,local=0,local_merges=0,rounds=0;double t_mirror=0,t_local=0,t_conflict=0,t_compat=0,t_implicit=0;};
class Run{public:const QAlg&Q;const vector<Obs>&obs;CarrierTheta&th;DSU g;std::unordered_map<uint64_t,int,H>node;std::vector<std::unique_ptr<DSU>> lds;uint64_t local=0,local_merges=0,compat_records=0,compat_groups=0,compat_unions=0,implicit_checks=0,implicit_unions=0;
 Run(const QAlg&q,const vector<Obs>&o,CarrierTheta&t):Q(q),obs(o),th(t),g(q.q),lds(1+2*q.q){for(int a=0;a<Q.q;a++)node[pc(0,a)]=a;for(auto&o0:obs){int a=Q.idxRoot[th.f(o0.a)],b=Q.idxRoot[th.f(o0.b)],y=Q.idxRoot[th.f(o0.y)];int nr=get(rowc(b),a),nc=get(colc(Q.q,a),b),ny=get(0,y);g.u(nr,nc);g.u(nr,ny);}}
 int get(int c,int a){uint64_t k=pc(c,a);auto it=node.find(k);if(it!=node.end())return it->second;int id=g.add();node[k]=id;if(c!=0)bridge(c,a,id);return id;}
 void bridge(int c,int a,int id){int cc,la;if(isrow(Q.q,c)){int b=ctx(Q.q,c);cc=colc(Q.q,a);la=b;}else if(iscol(Q.q,c)){int aa=ctx(Q.q,c);cc=rowc(a);la=aa;}else return;uint64_t k=pc(cc,la);int qn;auto it=node.find(k);if(it==node.end()){qn=g.add();node[k]=qn;}else qn=it->second;g.u(id,qn);}
 bool mirror(){bool ch=false;auto items=node;for(auto&kv:items){int c=pa(kv.first),a=pb(kv.first),id=kv.second;if(c==0)continue;int r=g.f(id);bridge(c,a,id);if(g.f(id)!=r)ch=true;}return ch;}
 bool conflict(vector<pair<int,int>>&out){std::unordered_map<int,int>first;bool any=false;for(int a=0;a<Q.q;a++){int r=g.f(get(0,a));auto it=first.find(r);if(it==first.end())first[r]=a;else if(it->second!=a){out.push_back({it->second,a});any=true;}}return any;}
 bool local_add_seed(int c,int x,int y){
  if(c==0||x==y)return false;
  if(!lds[c])lds[c]=std::make_unique<DSU>(Q.q);
  DSU &L=*lds[c];
  if(L.f(x)==L.f(y))return false;
  local++;
  bool ch=false;
  // Add kappa <- kappa join Theta(x,y) directly.  Since
  // Theta(x,y)=Theta(x join y,x) join Theta(x join y,y), it suffices
  // to union generator pairs for the two principal congruences into the
  // persistent local DSU; no temporary q-element DSU or full q scan is needed.
  auto add_pair=[&](int a,int b){
    int ra=L.f(a),rb=L.f(b);
    if(ra==rb)return;
    int na=get(c,a),nb=get(c,b);
    if(g.u(na,nb))ch=true;
    if(L.u(ra,rb)){local_merges++;ch=true;}
  };
  auto add_principal=[&](int u,int s){
    std::unordered_map<int,int> first;
    const bool discrete=(Q.q==Q.A.n);
    if(discrete){
      int os=Q.orig[s],ou=Q.orig[u];
      uint32_t known=Q.A.z[os]|Q.A.o[os], sub=known;
      // At most 2^w entries for KnownBits, only values a >= s occur.
      first.reserve((size_t)1u << std::min(Q.A.w,16));
      while(true){
        uint32_t zz=Q.A.z[os]&sub,oo=Q.A.o[os]&sub;
        int a=Q.A.index(zz,oo), key=Q.A.join(ou,a);
        auto it=first.find(key);
        if(it==first.end())first.emplace(key,a);else add_pair(it->second,a);
        if(sub==0)break; sub=(sub-1)&known;
      }
    }else{
      first.reserve(Q.q);
      for(int a=0;a<Q.q;a++){
        if(Q.join(s,a)!=a)continue;
        int key=Q.join(u,a);
        auto it=first.find(key);
        if(it==first.end())first.emplace(key,a);else add_pair(it->second,a);
      }
    }
  };
  int u=Q.join(x,y); add_principal(u,x); add_principal(u,y);
  return ch;
 }
 bool close_local(){std::unordered_map<int,vector<pair<int,int>>>comp;comp.reserve(node.size()/2+1);for(auto&kv:node){int c=pa(kv.first),a=pb(kv.first);if(c)comp[g.f(kv.second)].push_back({c,a});}bool ch=false;for(auto&kv:comp){std::unordered_map<int,int> first;first.reserve(kv.second.size());for(auto[c,a]:kv.second){auto it=first.find(c);if(it==first.end())first.emplace(c,a);else if(it->second!=a){if(local_add_seed(c,it->second,a))ch=true;}}}return ch;}
 bool compatibility_implicit_cells(){
  // For each actual component U and each row R_b / column K_a both represented in U,
  // combine U's pair (x,y) with the virtual physical-cell pair (a,b).
  std::unordered_map<int,vector<pair<int,int>>> comp; comp.reserve(node.size()/2+1);
  for(auto &kv:node){int c=pa(kv.first);if(c==0)continue;int a=pb(kv.first),r=g.f(kv.second);comp[r].push_back({c,a});}
  bool ch=false;
  for(auto &kv:comp){
    vector<pair<int,int>> rows,cols; std::unordered_map<int,int> first; first.reserve(kv.second.size());
    for(auto [c,v]:kv.second) if(!first.count(c)) first.emplace(c,v);
    for(auto &cv:first){int c=cv.first,v=cv.second;if(isrow(Q.q,c))rows.push_back({ctx(Q.q,c),v});else if(iscol(Q.q,c))cols.push_back({ctx(Q.q,c),v});}
    for(auto [b,x]:rows) for(auto [a,y]:cols){
      implicit_checks++;
      int jr=Q.join(x,a), jc=Q.join(y,b);
      int nr=get(rowc(b),jr), nc=get(colc(Q.q,a),jc);
      if(g.u(nr,nc)){ch=true;implicit_unions++;}
    }
  }
  return ch;
 }
 bool compatibility_components(){
  const int nc=1+2*Q.q;vector<vector<pair<int,int>>> by(nc);
  for(auto &kv:node){int c=pa(kv.first),a=pb(kv.first),r=g.f(kv.second);by[c].push_back({r,a});}
  for(auto &v:by){std::sort(v.begin(),v.end(),[](auto&A,auto&B){return A.first<B.first||(A.first==B.first&&A.second<B.second);});size_t w=0;for(size_t i=0;i<v.size();){size_t j=i+1;while(j<v.size()&&v[j].first==v[i].first)j++;v[w++]=v[i];i=j;}v.resize(w);}
  // Central copy is dense (q endpoints) and would alone contribute C(q,2) useless records per round.
  // Store its component->value map and inject it only for component pairs already co-occurring
  // in at least one non-central copy.
  std::unordered_map<int,int> central;central.reserve(by[0].size()*2+1);for(auto [r,v]:by[0])central.emplace(r,v);
  uint64_t rec_est=0;for(int c=1;c<nc;c++){uint64_t w=by[c].size();rec_est+=w*(w-1)/2;}
  vector<CompatRec> rec;rec.reserve(rec_est);
  for(int c=1;c<nc;c++){auto &v=by[c];for(size_t i=0;i<v.size();i++)for(size_t j=i+1;j<v.size();j++){int r1=v[i].first,r2=v[j].first;if(r1>r2)std::swap(r1,r2);int z=Q.join(v[i].second,v[j].second);rec.push_back({pc(r1,r2),(uint32_t)c,(uint32_t)z});}}
  compat_records+=rec.size();std::sort(rec.begin(),rec.end());bool ch=false;
  for(size_t i=0;i<rec.size();){size_t j=i+1;while(j<rec.size()&&rec[j].k==rec[i].k)j++;int r1=pa(rec[i].k),r2=pb(rec[i].k);auto c1=central.find(r1),c2=central.find(r2);bool hasC=(c1!=central.end()&&c2!=central.end());if((j-i)+(hasC?1:0)>=2){compat_groups++;int anchor=get((int)rec[i].c,(int)rec[i].v);for(size_t k=i+1;k<j;k++){int cur=get((int)rec[k].c,(int)rec[k].v);if(g.u(anchor,cur)){ch=true;compat_unions++;}}if(hasC){int zc=Q.join(c1->second,c2->second);int cur=get(0,zc);if(g.u(anchor,cur)){ch=true;compat_unions++;}}}i=j;}
  return ch;
 }
 RunRes run(){RunRes out;auto timed=[&](double &acc,auto fn){auto t0=std::chrono::steady_clock::now();bool r=fn();auto t1=std::chrono::steady_clock::now();acc+=std::chrono::duration<double,std::milli>(t1-t0).count();return r;};for(int rd=0;rd<100;rd++){out.rounds=rd+1;bool ch=false;if(timed(out.t_mirror,[&]{return mirror();}))ch=true;if(timed(out.t_local,[&]{return close_local();}))ch=true;vector<pair<int,int>>cp;if(timed(out.t_conflict,[&]{return conflict(cp);})){out.cp=cp;break;}if(timed(out.t_implicit,[&]{return compatibility_implicit_cells();}))ch=true;if(timed(out.t_compat,[&]{return compatibility_components();}))ch=true;if(timed(out.t_mirror,[&]{return mirror();}))ch=true;cp.clear();if(timed(out.t_conflict,[&]{return conflict(cp);})){out.cp=cp;break;}if(!ch)break;}out.endpoints=node.size();out.compat_records=compat_records;out.compat_groups=compat_groups;out.compat_unions=compat_unions;out.implicit_checks=implicit_checks;out.implicit_unions=implicit_unions;out.local=local;out.local_merges=local_merges;if(out.cp.empty()){std::unordered_map<int,int>cv;for(int y=0;y<Q.q;y++)cv[g.f(get(0,y))]=y;for(auto&kv:node){int c=pa(kv.first),a=pb(kv.first);if(c==0)continue;auto it=cv.find(g.f(kv.second));if(it==cv.end())continue;uint64_t cell;if(isrow(Q.q,c))cell=pc(a,ctx(Q.q,c));else if(iscol(Q.q,c))cell=pc(ctx(Q.q,c),a);else continue;out.known[cell]=it->second;}}return out;}
};
struct Sol{CarrierTheta th;RunRes rr;explicit Sol(const KBAlg&A):th(A){}};static Sol solve(const KBAlg&A,const vector<Obs>&obs){Sol S(A);int waves=0;while(true){QAlg Q(A,S.th);Run R(Q,obs,S.th);auto rr=R.run();if(rr.cp.empty()){S.rr=std::move(rr);break;}bool ch=false;for(auto[a,b]:rr.cp)if(S.th.add(Q.orig[a],Q.orig[b]))ch=true;if(!ch)throw std::runtime_error("feedback no progress");if(++waves>A.n+2)throw std::runtime_error("waves");}return S;}
int main(){try{string m;int ver,w,nobs;if(!(std::cin>>m>>ver>>w>>nobs)||m!="KBPQ"||ver!=1)throw std::runtime_error("KBPQ 1 width nobs");KBAlg A(w);vector<Obs>obs(nobs);for(auto&o:obs)std::cin>>o.a>>o.b>>o.y;auto t0=std::chrono::steady_clock::now();auto S=solve(A,obs);auto t1=std::chrono::steady_clock::now();auto bs=S.th.blocks();std::ostringstream out;out<<"{\"n\":"<<A.n<<",\"theta_blocks\":"<<bs.size()<<",\"known_count\":"<<S.rr.known.size()<<",\"stats\":{\"endpoints\":"<<S.rr.endpoints<<",\"compat_records\":"<<S.rr.compat_records<<",\"compat_groups\":"<<S.rr.compat_groups<<",\"compat_unions\":"<<S.rr.compat_unions<<",\"local_closures\":"<<S.rr.local<<",\"local_merges\":"<<S.rr.local_merges<<",\"rounds\":"<<S.rr.rounds<<",\"time_ms\":{\"mirror\":"<<S.rr.t_mirror<<",\"local\":"<<S.rr.t_local<<",\"conflict\":"<<S.rr.t_conflict<<",\"compat\":"<<S.rr.t_compat<<"}}}";std::cerr<<"solve_us="<<std::chrono::duration<double,std::micro>(t1-t0).count()<<"\n";std::cout<<out.str()<<"\n";return 0;}catch(const std::exception&e){std::cerr<<"component_pairs: "<<e.what()<<"\n";return 2;}}
