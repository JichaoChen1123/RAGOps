import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { CardStack } from '../../frontend/src/components/CardStack';

const records = Array.from({ length: 6 }, (_, index) => ({ id: `run-${index}`, label: `运行 ${index + 1}` }));
const props = { label: '运行', getLabel: (item: typeof records[number]) => item.label, renderItem: (item: typeof records[number]) => <a href={`#${item.id}`}>打开 {item.label}</a> };

describe('CardStack browsing and changing data', () => {
  it('caps visible sheets at three and only mounts the active record controls', () => {
    const { container } = render(<CardStack items={records} {...props} />);
    expect(container.querySelectorAll('.stack-sheet')).toHaveLength(3);
    expect(screen.getAllByRole('article')).toHaveLength(1);
    expect(screen.getAllByRole('link')).toHaveLength(1);
    expect(screen.getByRole('article')).toHaveAccessibleName('运行 1');
  });

  it('wraps with buttons and keyboard, supports Home/End and retains control focus', async () => {
    const user = userEvent.setup();
    render(<CardStack items={records} {...props} />);
    const next = screen.getByRole('button', { name: '运行：下一项' });
    await user.click(next);
    expect(screen.getByRole('article')).toHaveAccessibleName('运行 2');
    expect(next).toHaveFocus();
    await user.keyboard('{End}');
    expect(screen.getByRole('article')).toHaveAccessibleName('运行 6');
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('article')).toHaveAccessibleName('运行 1');
    await user.keyboard('{ArrowLeft}');
    expect(screen.getByRole('article')).toHaveAccessibleName('运行 6');
    await user.keyboard('{Home}');
    expect(screen.getByRole('article')).toHaveAccessibleName('运行 1');
    const region = screen.getByRole('region', { name: '运行' });
    region.focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('article')).toHaveAccessibleName('运行 2');
  });

  it('selects a rear sheet, retains identity on reorder and recovers when filtering removes it', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<CardStack items={records} {...props} />);
    await user.click(screen.getByRole('button', { name: '翻阅：运行 3' }));
    expect(screen.getByRole('article')).toHaveAccessibleName('运行 3');
    expect(screen.getByRole('region')).toHaveFocus();
    rerender(<CardStack items={[...records].reverse()} {...props} />);
    expect(screen.getByRole('article')).toHaveAccessibleName('运行 3');
    rerender(<CardStack items={[records[0]]} {...props} />);
    expect(screen.getByRole('article')).toHaveAccessibleName('运行 1');
    expect(screen.getByRole('button', { name: '运行：下一项' })).toBeDisabled();
    rerender(<CardStack items={[]} {...props} />);
    expect(screen.getByText('暂无可浏览记录。')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('does not intercept navigation keys from record content', async () => {
    const user = userEvent.setup();
    render(<CardStack items={records} {...props} renderItem={() => <input aria-label="备注" />} />);
    within(screen.getByRole('article')).getByRole('textbox').focus();
    await user.keyboard('{ArrowRight}{End}');
    expect(screen.getByRole('article')).toHaveAccessibleName('运行 1');
  });
});
