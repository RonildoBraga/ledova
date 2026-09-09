module LedovaCodegen
  def self.remove_directory_input(installer)
    installer.pods_project.targets.each do |target|
      next unless target.name == 'ReactCodegen'

      target.shell_script_build_phases.each do |phase|
        next unless phase.name == '[CP-User] Generate Specs'

        phase.input_paths.delete('${PODS_ROOT}/..')
      end
    end
  end
end
