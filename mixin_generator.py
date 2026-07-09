import ast
import os
import sys

"""
Mixin Generator Compiler for fabric-language-python.
This script acts as an AST (Abstract Syntax Tree) compiler. Since SpongePowered Mixins 
are deeply tied to Java bytecode and rely on Java annotations (@Inject, @Overwrite), 
it is impossible to write a Mixin natively in pure Python.

This script solves that by scanning the Python source code during the Gradle build phase,
looking for Python classes decorated with @Mixin. When it finds one, it extracts the 
Python AST and automatically generates a matching Java `.java` file. 
That generated Java file contains the actual Mixin annotations and acts as a bridge, 
forwarding the method calls back into the Python runtime using GraalPy's Context.
"""

def parse_files(src_dir, dest_dir):
    """
    Recursively scans the source directory for .py files, reads their content,
    and parses them into an Abstract Syntax Tree (AST) to look for Mixin definitions.
    """
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
        
    for root, dirs, files in os.walk(src_dir):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                try:
                    # Parse the raw Python source code into an AST tree
                    tree = ast.parse(content)
                    process_ast(tree, dest_dir, file_path)
                except SyntaxError as e:
                    print(f"Error parsing {file_path}: {e}")

def get_annotation_value(node):
    """
    Helper function to extract the value of a Python type annotation.
    For example, extracts 'CallbackInfo' from `def my_method(info: CallbackInfo)`.
    """
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.Name):
        return node.id
    return "Object" # Fallback type if no specific Java type is provided

def process_ast(tree, dest_dir, file_path):
    """
    Iterates over all top-level nodes in the parsed Python AST.
    If it finds a ClassDef (class declaration) that has a decorator named '@Mixin',
    it extracts the target Java class it is attempting to mix into.
    """
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            target_class = None
            # Scan the decorators of the class
            for dec in node.decorator_list:
                # Look for a decorator resembling @Mixin("net.minecraft....")
                if isinstance(dec, ast.Call) and getattr(dec.func, 'id', '') == 'Mixin':
                    if dec.args:
                        target_class = dec.args[0].value
            
            if target_class:
                # If a mixin target is found, trigger the Java generation process
                generate_java(node, target_class, dest_dir)

def generate_java(class_node, target_class, dest_dir):
    """
    Generates a raw .java file that matches the Python Mixin definition.
    This generated Java class uses standard SpongePowered Mixin annotations and 
    delegates execution back to the Python class at runtime via MixinBridge.
    """
    class_name = class_node.name
    java_code = []
    
    # Standard package and imports required by SpongePowered Mixins and our GraalPy Bridge
    java_code.append("package net.fabricmc.language.python.generated.mixins;")
    java_code.append("")
    java_code.append("import org.spongepowered.asm.mixin.*;")
    java_code.append("import org.spongepowered.asm.mixin.injection.*;")
    java_code.append("import org.spongepowered.asm.mixin.injection.callback.*;")
    java_code.append("import net.fabricmc.language.python.MixinBridge;")
    java_code.append("")
    
    # Class declaration with the @Mixin annotation pointing to the target Java class
    java_code.append(f"@Mixin({target_class}.class)")
    java_code.append(f"public class {class_name} {{")
    
    # Iterate over the methods defined inside the Python mixin class
    for item in class_node.body:
        if isinstance(item, ast.FunctionDef):
            decorators = []
            # Translate Python decorators (@Inject, @Overwrite) into Java annotations
            for dec in item.decorator_list:
                if isinstance(dec, ast.Call):
                    dec_name = dec.func.id
                    kwargs = []
                    # Parse kwargs like method="init", at=@At("HEAD")
                    for kw in dec.keywords:
                        if kw.arg == 'at' and isinstance(kw.value, ast.Constant):
                            kwargs.append(f'at = @At("{kw.value.value}")')
                        elif isinstance(kw.value, ast.Constant):
                            val = f'"{kw.value.value}"' if isinstance(kw.value.value, str) else str(kw.value.value).lower()
                            kwargs.append(f'{kw.arg} = {val}')
                        elif isinstance(kw.value, ast.Call):
                            at_args = []
                            # Positional args in Java annotations usually map to 'value'
                            for arg in kw.value.args:
                                if isinstance(arg, ast.Constant):
                                    aval = f'"{arg.value}"' if isinstance(arg.value, str) else str(arg.value)
                                    at_args.append(f'value = {aval}')
                            for akw in kw.value.keywords:
                                if isinstance(akw.value, ast.Constant):
                                    aval = f'"{akw.value.value}"' if isinstance(akw.value.value, str) else str(akw.value.value)
                                    at_args.append(f'{akw.arg} = {aval}')
                            kwargs.append(f'{kw.arg} = @{kw.value.func.id}({", ".join(at_args)})')
                    decorators.append(f"@{dec_name}({', '.join(kwargs)})")
            
            # If the method has valid Mixin decorators, we generate the Java proxy method
            if decorators:
                return_type = "void"
                if item.returns:
                    return_type = get_annotation_value(item.returns)
                
                args_list = []
                bridge_args = []
                # Map Python arguments to Java arguments
                for i, arg in enumerate(item.args.args):
                    if i == 0 and arg.arg == 'self':
                        continue # Skip 'self', since the context is passed via 'this'
                    
                    # By default, @Inject uses CallbackInfo
                    arg_type = "CallbackInfo" if "Inject" in decorators[0] else "Object"
                    if arg.annotation:
                        arg_type = get_annotation_value(arg.annotation)
                    
                    args_list.append(f"{arg_type} {arg.arg}")
                    bridge_args.append(arg.arg)
                
                # Write the translated Java annotations
                for dec in decorators:
                    java_code.append(f"    {dec}")
                
                # Write the Java method signature
                java_args = ", ".join(args_list)
                java_code.append(f"    public {return_type} {item.name}({java_args}) {{")
                
                # Create the delegation call to GraalPy via the MixinBridge
                # This passes control from the compiled Java Bytecode back into the dynamic Python runtime
                b_args = ", ".join(bridge_args)
                bridge_call = f"MixinBridge.invoke(\"{class_name}\", \"{item.name}\", this"
                if bridge_args:
                    bridge_call += f", {b_args}"
                bridge_call += ")"
                
                # Handle method returns
                if return_type != "void":
                    java_code.append(f"        return ({return_type}) {bridge_call};")
                else:
                    java_code.append(f"        {bridge_call};")
                java_code.append("    }")
                
    java_code.append("}")
    
    # Save the generated .java file into the correct package directory structure
    out_file = os.path.join(dest_dir, "net", "fabricmc", "language", "python", "generated", "mixins", f"{class_name}.java")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(java_code))
    
    print(f"[fabric-language-python] AST Generated Java Mixin for: {class_name}")

if __name__ == "__main__":
    # The script is invoked by Gradle during the build process
    # argv[1] is the source directory containing the Python files
    # argv[2] is the destination directory for the generated Java files
    src = sys.argv[1]
    dest = sys.argv[2]
    parse_files(src, dest)
