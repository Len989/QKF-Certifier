/** Declaration inventory only: parse, never analyze, compile or invoke candidates. */
import com.sun.source.tree.*;
import com.sun.source.util.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import javax.lang.model.element.Modifier;
import javax.tools.*;

public final class Inventory {
    static String quote(String s) {
        if (s == null) return "null";
        StringBuilder b = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default:
                    if (c < 32) b.append(String.format("\\u%04x", (int)c));
                    else b.append(c);
            }
        }
        return b.append('"').toString();
    }
    static String list(List<String> values) {
        StringJoiner b = new StringJoiner(",", "[", "]");
        for (String x : values) b.add(quote(x));
        return b.toString();
    }
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK compiler required");
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        try (StandardJavaFileManager fm = compiler.getStandardFileManager(diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            JavacTask task = (JavacTask) compiler.getTask(null, fm, diagnostics,
                    Arrays.asList("-proc:none", "--release", "17"), null,
                    fm.getJavaFileObjectsFromStrings(Arrays.asList(args)));
            Iterable<? extends CompilationUnitTree> units = task.parse();
            Trees trees = Trees.instance(task);
            DocTrees docs = DocTrees.instance(task);
            SourcePositions positions = trees.getSourcePositions();
            for (CompilationUnitTree unit : units) {
                String path = Paths.get(unit.getSourceFile().toUri()).toString();
                new TreePathScanner<Void, Void>() {
                    final List<String> classes = new ArrayList<>();
                    @Override public Void visitClass(ClassTree node, Void unused) {
                        classes.add(node.getSimpleName().toString());
                        super.visitClass(node, unused);
                        classes.remove(classes.size() - 1);
                        return null;
                    }
                    @Override public Void visitMethod(MethodTree node, Void unused) {
                        List<String> params = new ArrayList<>(), names = new ArrayList<>(), modifiers = new ArrayList<>();
                        for (VariableTree p : node.getParameters()) { params.add(p.getType().toString()); names.add(p.getName().toString()); }
                        for (Modifier m : node.getModifiers().getFlags()) modifiers.add(m.toString());
                        Collections.sort(modifiers);
                        long start = positions.getStartPosition(unit, node), end = positions.getEndPosition(unit, node);
                        long body = node.getBody() == null ? -1 : positions.getStartPosition(unit, node.getBody());
                        String doc = docs.getDocComment(getCurrentPath());
                        List<String> locals = new ArrayList<>();
                        if (node.getBody() != null) new TreeScanner<Void, Void>() {
                            @Override public Void visitVariable(VariableTree v, Void x) {
                                locals.add(v.getName().toString());
                                return super.visitVariable(v, x);
                            }
                        }.scan(node.getBody(), null);
                        System.out.println("{\"path\":" + quote(path) + ",\"class\":" + quote(String.join(".", classes))
                            + ",\"package\":" + quote(unit.getPackageName() == null ? "" : unit.getPackageName().toString())
                            + ",\"name\":" + quote(node.getName().toString()) + ",\"return_type\":" + quote(node.getReturnType() == null ? "<constructor>" : node.getReturnType().toString())
                            + ",\"parameter_types\":" + list(params) + ",\"parameter_names\":" + list(names)
                            + ",\"local_names\":" + list(locals) + ",\"modifiers\":" + list(modifiers) + ",\"start_utf16\":" + start + ",\"end_utf16\":" + end
                            + ",\"body_start_utf16\":" + body + ",\"doc\":" + quote(doc) + "}");
                        return super.visitMethod(node, unused);
                    }
                }.scan(unit, null);
            }
            boolean failed = false;
            for (Diagnostic<? extends JavaFileObject> d : diagnostics.getDiagnostics()) {
                System.err.println(d.toString());
                if (d.getKind() == Diagnostic.Kind.ERROR) failed = true;
            }
            if (failed) throw new IllegalStateException("declaration parsing errors; inventory is incomplete");
        }
    }
}
