import { useEnergySavingTasks } from '../../hooks/useEnergySavingTasks';

export const EnergySavingTaskWidget = () => {
  const { tasks, title, isLoading } = useEnergySavingTasks();

  if (isLoading && tasks.length === 0) {
    return <div className="widget-box" style={{ opacity: 0.7 }}>提案を取得しています...</div>;
  }
  if (tasks.length === 0) return null;

  return (
    <section>
      {/* 見出しはレベルによって変わるためサーバーから受け取る */}
      <div className="sec-title">{title}</div>
      <div>
        {tasks.map((task) => (
          // チェックボックス・完了操作は付けないこと（docs/design.md §1.2）
          <div key={task.id} className="suggest">
            <div className="suggest-text">{task.title}</div>
            {task.description && <div className="suggest-reason">{task.description}</div>}
          </div>
        ))}
      </div>
    </section>
  );
};
